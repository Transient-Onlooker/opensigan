# MVP 고정 버전의 Workers 로컬 실험

> 아래 실측과 기존 재현 명령은 **1.4.3 당시 기록**입니다. 현재 프로젝트는 1.4.4를 사용하며 이 기록만으로 새 버전의 통신 성공을 보장할 수 없습니다. 1.4.3 실험을 재현하려면 해당 버전이 남아 있는 과거 커밋을 사용해야 합니다.

## 현재 주 시간표 단회 실험 — 2026-11-10 KST

로컬 Python Workers에서 실제 학교 한 곳의 `TimeTable(학교명, week_num=0)`을 한 번 호출했다. 성공, 월~금 수업 1,182건, `replaced=True` 18건, 수업의 불리언 변경 표시 값 존재, 오류 유형 없음, Worker 처리 벽시계 920ms다. 수업은 과목 또는 교사 값이 있거나 변경 표시가 참인 교시이며 빈 교시는 제외한다. 학교 전체 학년·반을 합산했다. 원본이나 학교·교사·반 식별정보는 기록하지 않았다. 표시 값의 존재와 참인 건수를 확인한 것이며 기준 시간표와 대조한 정확도 검증은 아니다.

한 번의 공개 API 호출은 내부 서비스 페이지, 학교 검색 및 시간표 HTTP 요청을 포함할 수 있다. HTTP 횟수는 계측하지 않았다. 학교명이 유일하지 않으면 조회가 실패할 수 있다. 예외는 메시지 없이 유형만 저장하므로 upstream이 모두 `RuntimeError`로 바꾸는 403과 429는 이 기록만으로 구별하지 못한다. 자동 재시도는 없다. 새 프로세스를 실행하면 다시 호출 가능하므로 재현 실행도 별도의 실제 외부 조회다. 로컬 단일 표본으로 실제 Cloudflare 환경, CPU·메모리, 반복 안정성, 변경 표시의 의미나 정확도를 증명하지 않는다.

기존 wheel 준비와 해시 검증은 [COMPATIBILITY.md](COMPATIBILITY.md)를 따른다. `phase0-mvp`에서 아래 실행 시 유일하게 검색되는 학교명을 직접 입력한다. 이름은 요청 본문으로 로컬 Worker에만 전달하며 파일·명령줄 인수에 저장하지 않는다. 실행 전 원본 이용 조건을 확인한다.

```powershell
$env:OPENSIGAN_SCHOOL = Read-Host '조회할 학교명'
try { python run_local.py --timetable } finally { Remove-Item Env:OPENSIGAN_SCHOOL }
```

기동 대기 최대 60초, 로컬 요청 대기와 프로세스 트리 종료 watchdog 45초, 종료 확인 최대 10초다. upstream 각 HTTP 요청의 timeout은 30초이며 전체 45초 제한이 먼저 걸릴 수 있다. 각 Worker isolate의 시도 플래그는 서버 재시작이나 isolate 교체를 넘는 전역 제한이 아니다. runner는 로컬 요청을 한 번만 보낸다. 결과는 무시 대상 `run-result.json`, 제한된 이벤트는 `run.log`에 덮어쓴다. 프로세스 종료는 `server_stopped`와 종료 코드로 기록하며 강제 종료 코드 1은 API 실패를 뜻하지 않는다. 이번 실행 후 포트 18787 수신 프로세스가 없음을 확인했다. `elapsed_ms`는 Worker 요청 처리 벽시계이며 서버 기동·번들 준비, CPU 시간은 포함하지 않는다.

> 이전 결과: 초기 실패 이후 자체 빌드 wheel로 로컬 Workers import·AES와 검색 API 1회가 성공했다. 시간표 후속 결과는 위를 따른다. 아래의 초기 실패와 기존 실행 설명은 당시 기록이다.

2026-11-10에 MVP와 같은 `pycomcigan` Git 커밋 `e8ceaec7bad47cef946ec0174cc523f3652f42ee`의 소스로 wheel을 빌드했다. 캐시 체크아웃의 `git rev-parse HEAD`로 커밋을 확인했고 추적 파일 변경은 없었다. 빌드 결과는 `wheelhouse/pycomcigan-1.4.3-py3-none-any.whl`, SHA-256은 `9a3aa5c8eafd95d29f574941b4264f26480e7fc51ec5be45e37a2462b7dd85d9`다. `pyproject.toml`의 `tool.uv.sources`가 이 로컬 파일을 가리키며 `uv.lock`에도 경로와 해시가 기록된다.

이전 Git 직접 참조는 `uv pip compile --no-build`의 소스 빌드 금지에 걸렸다. wheel 적용 후 같은 CPython 3.14.2 Emscripten 대상에서 `--no-deps --no-build` 해석은 wheel을 선택하고 성공했다. 당시 전체 로컬 Workers 준비는 후속 의존성 `pycryptodomex>=3.23`에 해당 대상의 사용 가능한 wheel이 없어 실패했다. 서버 종료 코드는 1이고 검색 API 호출은 **0회**였다. 당시 실행 원문은 Git에 올리지 않았다. 이는 당시 패키지 해석 결과이며 네트워크나 CPU 호환성 판정은 아니다. 원격 배포는 하지 않았다.

## Windows 재현

Python 3.13.14, uv 0.13.4, workers-py/pywrangler 1.17.9, workers-runtime-sdk 1.9.6을 사용했다. Wrangler 버전은 이 프로젝트에서 고정하지 않았다. 패키지 도구 및 Workers 런타임 준비에 네트워크가 필요할 수 있다. 아래는 `phase0-mvp` 디렉터리에서 PowerShell로 실행한다. 저장된 wheel은 먼저 해시를 확인한다.

```powershell
Get-FileHash -Algorithm SHA256 .\wheelhouse\pycomcigan-1.4.3-py3-none-any.whl
uv sync --locked
.\.venv\Scripts\uv.exe pip compile pyproject.toml --python cpython-3.14.2-emscripten-wasm32-musl --no-deps --no-build --no-header
.\.venv\Scripts\python.exe run_local.py
```

마지막 명령은 기동을 최대 60초 기다리고, 준비되면 `get_school_code("서울")`을 **한 번만** 호출하는 로컬 요청을 한 번 보낸다. 응답은 최대 45초 기다린 뒤 프로세스 트리를 종료하며 자동 재시도하지 않는다. 단일 API 호출은 내부적으로 여러 원본 HTTP 요청을 할 수 있다. 실행 전 원본 이용 조건을 확인하고, 이전 실행에서 검색이 발생했는지 확인한 후에만 실행한다. 새 서버 실행은 별도의 검색 기회이므로 반복 실행하지 않는다. `run.log`와 무시 대상인 `run-result.json`은 매 실행 덮어쓴다. 실패 시 runner 종료 코드는 1이다. 원본 응답과 학교 식별정보는 기록하지 않는다.

wheel 재생성이 필요하면 다음 명령을 `phase0-mvp`에서 실행한다. 지정된 임시 디렉터리는 미리 존재하지 않아야 한다.

```powershell
git clone https://github.com/hegelty/pycomcigan.git "$env:LOCALAPPDATA\Temp\opensigan-wheel-source"
git -C "$env:LOCALAPPDATA\Temp\opensigan-wheel-source" checkout --detach e8ceaec7bad47cef946ec0174cc523f3652f42ee
git -C "$env:LOCALAPPDATA\Temp\opensigan-wheel-source" rev-parse HEAD
git -C "$env:LOCALAPPDATA\Temp\opensigan-wheel-source" status --short
.\.venv\Scripts\uv.exe build "$env:LOCALAPPDATA\Temp\opensigan-wheel-source" --wheel --out-dir wheelhouse
Get-FileHash -Algorithm SHA256 .\wheelhouse\pycomcigan-1.4.3-py3-none-any.whl
.\.venv\Scripts\uv.exe lock
```

커밋과 추적 파일의 변경 여부를 확인한 후 빌드한다. 빌드 도구가 필요할 수 있다. wheel 해시는 제공된 산출물의 식별값이며 서로 다른 빌드 환경에서 바이트 단위 재현성은 검증하지 않았다.

기본 샌드박스에서 uv 캐시 잠금 접근은 `액세스가 거부되었습니다. (os error 5)`로 실패했다. 격리 캐시와 기존 전역 캐시를 사용하는 오프라인 빌드는 각각 `poetry-core`가 캐시에 없다는 의존성 해석 오류로 실패했다. 캐시 잠금 권한을 허용한 뒤 빌드 도구를 준비하여 wheel 빌드에 성공했다. Workers 실행에도 같은 캐시 잠금 권한이 필요했다.
