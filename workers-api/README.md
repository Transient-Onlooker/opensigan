# Local Workers API spike

## Cloudflare deployment, 2026-11-10

The Worker `opensigan-workers-api` and D1 database `opensigan-cache` are deployed. `wrangler.production.toml` records the non-secret bindings and Pages origin. The NEIS key has not been registered on the Worker; the repository secret is separate and does not automatically reach it. From `workers-api`, register the key interactively without putting it in a command or Git. This command uses the pinned Wrangler version through npm; paste the key only when Wrangler prompts for the secret value:

```powershell
npx --yes wrangler@4.159.0 secret put NEIS_API_KEY --config wrangler.production.toml
```

The deployed Worker returned 200 for status, the expected CORS header for the Pages origin, 503 for NEIS without a key, and 200 for one real school search and one current-week timetable (832 records). The initial search took approximately 23 seconds and a repeat returned in approximately 1.2 seconds; the timetable took approximately 4.8 seconds. These are individual wall-clock observations, not CPU measurements or a reliability benchmark. The NEIS path, distributed D1 concurrency and Cloudflare resource limits remain unverified. Do not interpret availability as permission to redistribute provider data.

To redeploy, first create a fresh stage with `stage-repro.ps1` below. Copy `wrangler.production.toml` into its `bundle` directory, then run the stage's `node_modules/.bin/wrangler` with `deploy --config <stage>/bundle/wrangler.production.toml`. This bundles the pinned Python dependencies and backend modules. Never copy `.env` or the NEIS key into the bundle. The local-only instructions and observations below remain relevant to reproducibility, but statements about no remote deployment describe the earlier experiments.

The local Worker observations below were made with pycomcigan 1.4.3 unless explicitly stated otherwise. Version 1.4.4 changes the upstream HTTP transport; those earlier observations do not establish its runtime compatibility.

`worker.py` imports the existing timetable functions from `../backend/timetable.py` and `NEISClient` and `School` from `../backend/neis.py`. The source of truth stays there. Wrangler 4.159.0 does not recurse into the existing Windows `backend` junction when collecting Python modules, so importing from that junction fails in the actual Worker bundle. The CPython tests alone cannot detect this: they add the repository root to `sys.path`.

The historical `stage-local.ps1` creates a new ignored `.runtime/stage-<id>` and copies `worker.py`, `d1_cache.py`, `schema.sql`, and the original `backend/timetable.py` and `backend/neis.py` into ordinary directories there. It copies the already-synced `python_modules`, and links the existing `.venv-workers` and local Wrangler `node_modules`. These are build inputs, not independently maintained project source. The script checks both sync tokens against `pyproject.toml`, `pylock.toml`, and pywrangler 1.17.9. It requires already-prepared dependencies; if they are missing or stale, prepare them separately before running. The staged `pyproject.toml` retains its original relative wheel path and is not intended for a fresh sync inside the stage. For a fresh dependency sync, use `stage-repro.ps1` below.

The NEIS endpoints use only the Workers `env.NEIS_API_KEY` binding; the key is never returned to callers. `/api/v1/neis/schools?q=...` returns school candidates, and `/api/v1/meals?school=B10:1234567&from=YYYY-MM-DD&to=YYYY-MM-DD` requires a NEIS office/school pair and an inclusive range of at most seven days. Bad inputs return 400; a missing key or unavailable cache/upstream returns 503. Avoid putting secrets in source, client code, URLs sent to this Worker, or logs.

For a separately hosted browser frontend, set the Worker `CORS_ALLOWED_ORIGIN` binding to exactly one origin (scheme, host, and optional port; no path), such as `https://transient-onlooker.github.io`. Only requests whose `Origin` exactly matches that value receive `Access-Control-Allow-Origin`; unset configuration disables browser cross-origin access. Matching `OPTIONS` requests receive a 204 preflight response allowing `GET` and the `Accept` header. Other origins get no CORS permission (and preflight receives 403). All responses include `Vary: Origin`; JSON responses are `no-store`, so cached API data is not shared by HTTP caches across origins.

Local Wrangler verification on 2026-11-10 confirmed the allowed-origin preflight returned an empty 204 and an invalid GET returned 400 with the CORS header; a different origin received no CORS permission. These requests did not contact an upstream service.

On 2026-11-10, a local Wrangler Worker with the local D1 schema wrote fixture school-search, NEIS school and meal results and returned each on a second request even though the fixtures would fail if called again. The NEIS fixture also exercised response parsing and meal splitting; D1 rows were present with their refresh locks released. This checks the Python D1 binding, SQL and cache hits locally; it does not validate distributed D1 behavior or real upstream traffic.

School searches, timetables, NEIS searches and meals require `env.DB` and use D1 with a 30-minute TTL. Expired results are served with `stale: true` for up to seven days after expiry when a refresh fails or another request holds the lease; without a usable previous result, duplicate requests and failure backoff return 503. Cache errors never trigger an unrestricted upstream bypass. Leases last 120 seconds, are not renewed, and fence expired owners from writing; a slow provider may still overlap a takeover. Existing synchronous providers are unchanged.

Each isolate opportunistically prunes up to 100 abandoned rows on its first request and at six-hour intervals after success; failures retry after five minutes. Active leases, backoff and recent rate history are preserved. This is not a global schedule or storage limit; cleanup runs only with traffic. A local Python Worker with local D1 removed two expired fixture rows and preserved fresh and usable stale rows, active leases, backoff and recent rate history. Distributed Cloudflare D1 behavior remains unverified.

Cold requests encountering contention recheck the cache and lease for up to 150 ms for Comcigan or 1.2 seconds for NEIS, allowing a NEIS request arriving just after another to pass the one-second origin interval. Longer contention or failure backoff still returns 503. Stale data is returned immediately.

Each refresh requires an explicit origin group. The Worker assigns `comcigan` to school searches and timetables, and `neis` to NEIS searches and meals. One unexpired lease per origin is allowed across different keys in the same database; a key must retain the same origin. All callers for an origin must use the same database and a current UTC clock. This is a limit on leases, not a strict limit on actual upstream calls after lease expiry, a request-rate limit, or protection against callers that bypass this cache. SQLite/mock tests do not establish distributed D1 behavior.

Refresh lease acquisitions are also spaced by at least one second per origin according to the caller clock. This does not limit individual HTTP calls made inside a provider, callers bypassing the cache, or work still running after lease expiry. Deleting cache rows also deletes their rate history. In a local Worker and D1 fixture test on 2026-11-10, an immediate second school search returned 503, a cache hit returned 200, and a subsequent search succeeded after the interval. Distributed behavior remains unverified.

For a database created with the previous `origin` schema, `migrations/0001_request_rate_limit.sql` adds the rate timestamp and index once, preserving existing rows. Do not apply it to a database already created with the current `schema.sql`, or apply it twice. Stop old Workers before changing schemas; this migration has only been tested with SQLite, not remote D1.

On 2026-11-10, a local Python Worker and fresh local D1 using this origin schema returned a fixture school search from cache on its second request. Two concurrent distinct school searches returned one 200 and one 503; the latter succeeded on retry after the lease was released. This used one local runtime and a fixture provider, with no upstream requests; distributed D1 remains unverified.

The Worker injects a synchronous `requests` transport for NEIS with the provider's timeout and redirects disabled. HTTP errors and requests exceptions become sanitized network errors; urllib3 connection-pool debug logging is suppressed because the URL contains the NEIS key. A separate local experiment reported that `urllib.request` disconnected while `requests` returned a NEIS sample with HTTP 200/INFO-000; this integration itself has only mock coverage so far.

**Incomplete:** SQLite/mock tests do not establish Cloudflare D1 consistency, clock behavior, or distributed concurrency. The remote Worker and D1 have handled the limited real requests described above, but distributed behavior still needs validation. The all-zero database ID in the local configuration is a placeholder; the deployed database is configured separately in `wrangler.production.toml`.

## Recreate the local prototype database

The explicit `origin` column changes the schema; rerunning `schema.sql` against an old database does not add that column because the table already exists. Stop any local Worker using the old database. Follow the staging commands below to create a **new** stage, enter that stage, and run `pywrangler d1 execute opensigan-cache-local --local --file schema.sql` before starting the local Worker. The new stage has a fresh local database and an empty cache; the old stage and its data remain untouched. Use only the new stage's database with the new code, and do not mix old and new workers against the same database. This is a local prototype reset, not a migration or remote operation.

## Reproduce from a new stage on this Windows workspace

`stage-repro.ps1` preserves existing environments and creates a new `.runtime/repro-<id>` every time. It copies both backend modules and the two SHA-256-checked wheels, then uses empty stage-specific npm and uv caches and an empty managed Python directory. Online access to the package registries and Python distribution downloads is required. It installs Wrangler from `package-lock.json`, downloads CPython 3.14.7, and syncs the native and Pyodide environments using the Workers runtime lock seed. Pyodide 3.14.2 is selected by pywrangler for the configured compatibility date. Failures leave the stage in place for inspection. The script restores the caller's environment variables on exit.

The prerequisites are Node.js 26.13.0, npm 12.0.2 and an already installed pywrangler 1.17.9 executable with uv 0.13.4 beside it. The copied `uv.lock` describes host-tool dependencies; the script checks those two executable versions but does not bootstrap or verify their installation from that lock. `pylock.seed.toml` is the Workers runtime lock: the script replaces its placeholder wheel URI in the staged copy. The staged project substitutes `find-links` for its direct local wheel source; the source project and seed remain unchanged. The generated runtime lock records the stage's own wheel paths. Keep the lockfiles and wheelhouse together when copying this project.

The project requires Python 3.14, matching the Python 3.14.2 Pyodide runtime selected by the Wrangler compatibility date. The staged native environment uses CPython 3.14.7; the separately installed pywrangler executable can itself run under another Python version. The host `uv.lock` and the Workers runtime `pylock.seed.toml` serve different purposes. Changing the compatibility date or dependency versions may require updating both the version contract and runtime wheels.

On 2026-11-10, a fresh stage synchronized both environments successfully without Python version compatibility warnings. The Python 3.14.7 native environment passed the 47 Worker, cache and migration mock/SQLite tests. This does not establish distributed D1 behavior.

```powershell
$stage = & .\stage-repro.ps1 -Pywrangler '..\phase0-mvp\.venv\Scripts\pywrangler.exe'
$env:WRANGLER_SEND_METRICS = 'false'
$env:CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV = 'false'
$env:CLOUDFLARE_INCLUDE_PROCESS_ENV = 'false'
$env:TEMP = Join-Path $stage 'tmp'
$env:TMP = $env:TEMP
$env:XDG_CONFIG_HOME = Join-Path $stage 'config'
Set-Location (Join-Path $stage 'bundle')
& '..\node_modules\.bin\wrangler.cmd' d1 execute opensigan-cache-local --local --file schema.sql
& '..\node_modules\.bin\wrangler.cmd' dev --local --ip 127.0.0.1 --port 18788
```

The separate `bundle` contains only the Worker files, backend modules and generated `python_modules`; running Wrangler from the stage root would also bundle the caches and virtual environment. Run Wrangler directly from `bundle`: do not run `pywrangler dev` there, because it would try to resync the intentionally isolated bundle. In a second terminal, request only `/api/v1/status`, `/api/v1/schools` without a query, and `/api/v1/timetable?school=0%3Aschool&week=bad`, then stop the server. These exercise liveness and validation without contacting providers.

On 2026-11-10, the online preparation procedure downloaded dependencies into a fresh stage, initialized a fresh local D1, and started Wrangler 4.159.0. The three requests returned 200, 400 and 400 respectively. No provider request or remote deployment was made.

## Historical staging procedure

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
