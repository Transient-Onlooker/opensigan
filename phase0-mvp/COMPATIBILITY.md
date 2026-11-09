# Phase 0: 고정 upstream의 Workers 패키징 판정

## 추가 실험: 로컬 PyEmscripten wheel — 2026-11-10

제공된 `pycryptodomex-3.24.2-cp37-abi3-pyemscripten_2026_0_wasm32.whl`을 `wheelhouse/`에 복사했다. SHA-256은 `f2c5fdc9fe8ba8ea5b827dc04fe06ad2d47e96ecbba58494bb6d5794439602b5`다. 자체 빌드 실험 산출물로 Git 무시 대상이다. 소스 sdist SHA-256은 `e4dbc29e2575365d15e272f769329106277649aea081e2119cf43d66950f8f8f`다. 제공자의 별도 Pyodide AES 성공 보고와 별개로 이번에 Workers 내부 AES를 검사했다.

`[tool.uv] find-links`로 wheelhouse를 검색한다. Pyodide 3.14.2 대상 pywrangler 해석·설치가 성공했고, 무시 대상 `pylock.toml`에 해당 로컬 wheel과 위 SHA-256이 기록됐다. 이 lock의 절대 경로는 다른 컴퓨터에서 재생성해야 한다. Windows 개발 환경용 `uv.lock`의 `uv lock --check --offline`도 통과했다. 별도의 오프라인 전체 해석은 wheel 문제를 넘은 뒤 캐시에 없는 requests 및 charset-normalizer 때문에 실패했으나, 온라인 의존성 준비를 사용하는 로컬 실행은 성공했다.

| 검증 | 결과 |
|---|---|
| `run_local.py --import-only` | 로컬 Workers에서 `get_school_code`·`Cryptodome.Cipher.AES` import 및 AES-128 ECB 알려진 정답 벡터 통과. 로컬 GET 200, Wrangler 기록 714ms. 원본 호출 0회. |
| `run_local.py` | 별도 로컬 서버에서 `get_school_code("서울")` 1회 성공, 10건, Worker 벽시계 755ms, 오류 없음. 로컬 GET 200, Wrangler 기록 788ms. 재시도 없음. |
| 종료 | 두 실행의 서버 종료 코드 1은 정리 시 프로세스 트리를 종료한 결과다. 검색 후 18787 포트에 LISTENING은 없고 TIME_WAIT만 관찰했다. |

API 한 번은 원본 HTTP 요청 한 번과 같지 않다. 라이브러리는 서비스 페이지와 검색을 순차적으로 요청하며 리디렉션이 있으면 교환이 더 늘 수 있다. 실제 HTTP 횟수는 계측하지 않았다. 개별 requests timeout은 30초, runner의 서버 준비 제한은 60초이며 로컬 요청은 소켓 timeout 45초와 45초 후 프로세스 트리 종료 watchdog을 사용한다. 종료 명령 실패까지 방지한다는 보장은 없다. 워커 전역 플래그는 인스턴스 내 재호출만 막으므로 새 서버 실행으로 다시 요청하지 말 것. 403/429 구분은 이번 성공 사례에서 검증되지 않았다.

재현은 Windows PowerShell에서 `phase0-mvp`를 작업 디렉터리로 한다. 제공된 파일과 다운로드 가능한 도구·의존성이 필요하다. 마지막 명령은 실제 원본을 다시 호출하므로 **새로운 호출이 별도로 허용될 때만** 한 번 실행한다. import-only는 원본에 접근하지 않는다. 로그와 결과 JSON은 덮어쓰며 Git에서 무시된다.

```powershell
Get-FileHash -Algorithm SHA256 "$env:LOCALAPPDATA\Temp\opensigan-pyodide-probe\wheelhouse\pycryptodomex-3.24.2-cp37-abi3-pyemscripten_2026_0_wasm32.whl"
Copy-Item -LiteralPath "$env:LOCALAPPDATA\Temp\opensigan-pyodide-probe\wheelhouse\pycryptodomex-3.24.2-cp37-abi3-pyemscripten_2026_0_wasm32.whl" -Destination .\wheelhouse\
Get-FileHash -Algorithm SHA256 .\wheelhouse\pycryptodomex-3.24.2-cp37-abi3-pyemscripten_2026_0_wasm32.whl
uv sync --locked
.\.venv\Scripts\python.exe run_local.py --import-only
# 별도 원본 호출 허용 시에만, 재시도 없이 1회:
.\.venv\Scripts\python.exe run_local.py
```

성공은 로컬 Workers 단일 표본이다. 실제 Cloudflare 배포, CPU·메모리, 반복 안정성, 시간표·변경 표시, 오류·타임아웃 처리 및 운영 적합성은 검증하지 않았다. 원격 배포나 원본 데이터 저장은 하지 않았다.

---

이하 내용은 wheel 통합 전의 조사 및 당시 실패 기록이다.

2026-11-10 로컬 조사. 판정은 **보류**다. 원본을 수정하지 않은 wheel로 Git 소스 빌드 장애는 통과했지만, MVP에 필요한 전체 의존성을 설치하거나 Workers에서 해당 버전을 실행하는 데는 아직 성공하지 못했다. 별도 배포나 원본 서버 요청은 이번 조사에서 하지 않았다.

## 범위와 결과

기획서는 원본 라이브러리를 수정하지 않고 Workers에서 패키징, 4082 포트 통신, 오류 처리, 시간표와 변경 표시를 검증하고 실제 환경의 CPU·메모리를 측정하도록 한다. 이 문서는 그중 로컬 패키징 단계의 증거다. MVP는 `pycomcigan` 커밋 `e8ceaec7bad47cef946ec0174cc523f3652f42ee`를 고정한다. 이전 `phase0`의 1.4.2 import 성공은 이 1.4.3 커밋에 대한 증거가 아니다.

기존 실험에서 위 커밋으로 빌드한 `wheelhouse/pycomcigan-1.4.3-py3-none-any.whl`의 SHA-256은 `9a3aa5c8eafd95d29f574941b4264f26480e7fc51ec5be45e37a2462b7dd85d9`다. 이번에 다시 해시를 확인했다. `uv 0.13.4`, Python 대상 `cpython-3.14.2-emscripten-wasm32-musl`에서 로컬 캐시만 사용해 다음을 확인했다.

| 검사 | 관찰 | 의미 |
|---|---|---|
| `--no-deps --no-build` | 해당 로컬 wheel 선택 성공 | Git 소스 빌드 차단을 패키징으로 우회. 실행 성공은 아님 |
| 전체 의존성 `--no-build` | `pycryptodomex>=3.23.0 has no usable wheels` | 로컬 캐시만으로 해석 실패. 오프라인 검사만으로 모든 외부 저장소에 wheel이 없다고 단정할 수 없음 |
| 기존 실행 기록 | Pyodide 인덱스를 포함한 전체 해석이 같은 오류로 중단, 서버 기동 전 종료 | 당시 검색 API 호출 0회. 이번에 실서버를 재호출하지 않음 |

재현 명령은 이 디렉터리에서 다음과 같다. 마지막 명령은 실패가 예상되며, 오프라인 캐시 상태에 따라 결과가 달라질 수 있다. 캐시 잠금 권한이 필요할 수 있다. 이 명령들은 Worker 또는 원본 서버를 실행하지 않는다.

```powershell
Get-FileHash -Algorithm SHA256 .\wheelhouse\pycomcigan-1.4.3-py3-none-any.whl
.\.venv\Scripts\uv.exe pip compile pyproject.toml --python cpython-3.14.2-emscripten-wasm32-musl --no-deps --no-build --no-header --offline --cache-dir .runtime\cache
.\.venv\Scripts\uv.exe pip compile pyproject.toml --python cpython-3.14.2-emscripten-wasm32-musl --extra-index-url https://index.pyodide.org/314.0.7 --index-strategy unsafe-best-match --no-header --no-build --offline --cache-dir .runtime\cache
```

## 장애와 대안

wheel 메타데이터의 필수 의존성은 `pycryptodomex>=3.23,<4`와 `requests>=2.32.4,<3`이다. 실제 wheel의 `_aes.py`는 `Cryptodome.Cipher.AES`를 가져온다. `pycryptodomex`의 Windows/Linux 네이티브 wheel은 WASM용이 아니다. [Cloudflare 공식 문서](https://developers.cloudflare.com/workers/languages/python/packages/)는 순수 Python wheel, PyEmscripten wheel 및 Pyodide 포함 패키지를 지원한다고 설명한다. [Pyodide 314 패키지 목록](https://pyodide.org/en/stable/usage/packages-in-pyodide.html)에는 `pycryptodome` 3.23.0이 있으나, [두 배포물의 공식 설치 문서](https://pycryptodome.readthedocs.io/en/v3.20.0/src/installation.html)에 따르면 각각 `Crypto`와 `Cryptodome` 네임스페이스를 제공하므로 이름만 바꿔 설치해서는 이 의존성을 충족하지 않는다.

실용적인 다음 후보는 **원본 소스를 변경하지 않고 공식 Pyodide 빌드 도구로 `pycryptodomex` 자체의 PyEmscripten wheel을 빌드하거나, 해당 wheel을 유지관리자로부터 제공받는 것**이다. Python 3.14의 `pyemscripten_2026_0_wasm32` ABI 및 실제 Pyodide 버전에 맞춰야 한다. [Pyodide 빌드 문서](https://pyodide.org/en/stable/development/building-packages.html)와 [플랫폼 ABI 문서](https://pyodide.org/en/stable/development/abi.html)를 따른다. 이 후보는 아직 빌드·설치·AES 검증을 통과한 산출물이 아니며, 일반적인 wheel 지원이 해당 wheel의 존재나 정상 작동을 보장하지 않는다. 배포물 이름이나 내부 네임스페이스를 위장하는 방식은 선택하지 않았다.

조사 당시 `pyodide` CLI 0.5.0은 있었지만 `pyodide-build` 모듈과 `emcc`는 확인되지 않았고, 프로젝트 내 격리 폴더와 uv 캐시 검색에서도 `pycryptodomex` WASM wheel 또는 sdist를 찾지 못했다. WSL 열거는 권한 오류라 설치 여부를 판단하지 못했다. 공식 Pyodide 빌드 안내는 Linux/macOS 환경을 요구한다. 따라서 공식 빌드 경로는 재현 가능한 다음 실험안으로 좁혀졌으나, 이 Windows 환경에서 wheel을 산출하는 것까지 실증하지는 못했다. upstream sdist의 해시를 먼저 검증하고 Linux 빌더에서 고정된 Pyodide xbuildenv로 빌드하는 것이 후속 spike의 최소 단계다.

wheel이 준비되면 별도 스파이크에서 원본과 빌드 도구 버전·해시를 기록하고, 전체 의존성 해석과 로컬 Worker import, 공개 AES 테스트 벡터를 먼저 검증한다. 그 후에만 기존 `run_local.py`의 제한을 사용해 원본 이용 조건을 확인하고 단회 API 호출을 검토한다. API 한 번이 HTTP 요청 한 번을 뜻하지는 않는다. 403/429에는 재시도하지 않는다. 상세 제한은 [README](README.md)를 따른다.

## 미검증

고정 1.4.3의 Workers import, AES, 동기 `requests`, 4082 연결, 학교 검색·시간표·변경 표시, 타임아웃 및 실패 처리, 실제 Cloudflare CPU·메모리·지연은 미검증이다. 로컬 벽시계 시간은 CPU 시간이 아니며, 원격 배포가 금지된 이번 작업에서는 실제 Workers 운영 한도도 측정할 수 없다. 호환성이 끝내 성립하지 않으면 이미 로컬에서 검증한 CPython 백엔드를 관리형 환경에 두는 대안을 비용·운영 부담과 함께 별도로 평가한다. 그 대안도 이 문서에서 배포하거나 운영 검증하지 않았다.
