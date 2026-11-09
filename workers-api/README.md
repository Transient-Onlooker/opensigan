# Local Workers API spike

`worker.py` imports the existing timetable functions from `../backend/timetable.py` and `NEISClient` and `School` from `../backend/neis.py`. The source of truth stays there. Wrangler 4.159.0 does not recurse into the existing Windows `backend` junction when collecting Python modules, so importing from that junction fails in the actual Worker bundle. The CPython tests alone cannot detect this: they add the repository root to `sys.path`.

`stage-local.ps1` creates a new ignored `.runtime/stage-<id>` on each run and copies `worker.py`, `d1_cache.py`, `schema.sql`, and the original `backend/timetable.py` and `backend/neis.py` into ordinary directories there. It copies the already-synced `python_modules`, and links the existing `.venv-workers` and local Wrangler `node_modules`. These are build inputs, not independently maintained project source. The script checks both sync tokens against `pyproject.toml`, `pylock.toml`, and pywrangler 1.17.9. It requires already-prepared dependencies; if they are missing or stale, prepare them separately before running. The staged `pyproject.toml` retains its original relative wheel path and is not intended for a fresh sync inside the stage.

The NEIS endpoints use only the Workers `env.NEIS_API_KEY` binding; the key is never returned to callers. `/api/v1/neis/schools?q=...` returns school candidates, and `/api/v1/meals?school=B10:1234567&from=YYYY-MM-DD&to=YYYY-MM-DD` requires a NEIS office/school pair and an inclusive range of at most seven days. Bad inputs return 400; a missing key or unavailable cache/upstream returns 503. Avoid putting secrets in source, client code, URLs sent to this Worker, or logs.

On 2026-11-10, a local Wrangler Worker with the local D1 schema wrote fixture school-search, NEIS school and meal results and returned each on a second request even though the fixtures would fail if called again. The NEIS fixture also exercised response parsing and meal splitting; D1 rows were present with their refresh locks released. This checks the Python D1 binding, SQL and cache hits locally; it does not validate distributed D1 behavior or real upstream traffic.

School searches, timetables, NEIS searches and meals require `env.DB` and use D1 with a 30-minute TTL. Expired results are served with `stale: true` when a refresh fails or another request holds the lease; without a previous result, duplicate requests and failure backoff return 503. Cache errors never trigger an unrestricted upstream bypass. Leases last 120 seconds, are not renewed, and fence expired owners from writing; a slow provider may still overlap a takeover. Stale data has no maximum age. Existing synchronous providers are unchanged.

The Worker injects a synchronous `requests` transport for NEIS with the provider's timeout and redirects disabled. HTTP errors and requests exceptions become sanitized network errors; urllib3 connection-pool debug logging is suppressed because the URL contains the NEIS key. A separate local experiment reported that `urllib.request` disconnected while `requests` returned a NEIS sample with HTTP 200/INFO-000; this integration itself has only mock coverage so far.

**Incomplete:** SQLite/mock tests do not establish Cloudflare D1 consistency, Python binding compatibility, clock behavior, or distributed concurrency. Validate those in an authorized distributed environment before relying on this cache. The all-zero database ID below is a local placeholder, not a provisioned remote database. No remote deployment is authorized by these instructions.

## Reproduce on this Windows workspace

From `workers-api` in PowerShell, with the existing `phase0-mvp` tools, workers-api synced dependencies, and cached Wrangler 4.159.0 available:

```powershell
$root = (Get-Location).Path
$stage = & .\stage-local.ps1 -WranglerModules '..\phase0-mvp\.runtime\npm\_npx\32026684e21afda6\node_modules'
New-Item -ItemType Directory -Force -Path "$root\.runtime\tmp", "$root\.runtime\config" | Out-Null
$env:TEMP = "$root\.runtime\tmp"
$env:TMP = $env:TEMP
$env:XDG_CONFIG_HOME = "$root\.runtime\config"
$env:npm_config_offline = 'true'
$env:UV_OFFLINE = '1'
$env:WRANGLER_SEND_METRICS = 'false'
$env:PATH = "$root\..\phase0-mvp\.venv\Scripts;$env:PATH"
Set-Location $stage
pywrangler d1 execute opensigan-cache-local --local --file schema.sql
pywrangler dev --local --ip 127.0.0.1 --port 18788
```

In a second terminal, send only these local requests, then stop the first terminal's server with Ctrl+C:

```powershell
curl.exe --noproxy '*' -i 'http://127.0.0.1:18788/api/v1/status'
curl.exe --noproxy '*' -i 'http://127.0.0.1:18788/api/v1/schools'
curl.exe --noproxy '*' -i 'http://127.0.0.1:18788/api/v1/timetable?school=0%3Aschool&week=bad'
curl.exe --noproxy '*' -i 'http://127.0.0.1:18788/api/v1/timetable?school=1%3Aschool&week=bad'
```

The cached Wrangler path is specific to this workspace. The script accepts another existing `node_modules` directory containing `.bin/wrangler.cmd`; offline mode requires its complete dependencies. Avoid valid school/search requests during this offline check because they can call the upstream service.

## Observed result, 2026-11-10

The script created `.runtime/stage-2aec70620f6145f39e24907352b790fb`. pywrangler 1.17.9 / Wrangler 4.159.0 listed `backend/timetable.py` as an attached Python module and started the local server. The four requests above returned respectively `200 {"status": "ok", "scope": "process liveness"}`, `400 {"error": "invalid q"}`, `400 {"error": "invalid school identifier"}`, and `400 {"error": "주 시작일이 올바르지 않습니다"}`. The server was stopped afterward. No upstream request or remote deployment was made.

The offline CPython handler tests also passed (3 tests):

```powershell
..\phase0-mvp\.venv\Scripts\python.exe -B test_worker.py
```

The above is a historical pre-cache observation. Status is process liveness only; valid upstream requests, performance, distributed concurrency, production logging, and remote deployment remain unverified. Each fresh stage has separate local D1 state; initialize its schema before starting it.

## NEIS local checks, 2026-11-10

The CPython mock contract suite passed (5 tests). The staged local Worker attached both backend modules. With no NEIS key configured, invalid NEIS search, school identifier, and date-range requests returned 400; valid-shaped school search and meal requests returned 503; the status endpoint still returned 200. These checks made no NEIS request. A successful real NEIS call, including compatibility of the existing synchronous transport with the Workers runtime, has not been verified with an authorized key. No remote deployment was made.
