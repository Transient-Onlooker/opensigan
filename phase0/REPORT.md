# Phase 0 근거 및 판정 — 2026-11-10 KST

> 추가 검증: 이 스파이크는 PyPI 1.4.2를 대상으로 한다. 별도의 로컬 MVP는 upstream 기본 브랜치 커밋 `e8ceaec7bad47cef946ec0174cc523f3652f42ee`를 사용하며, 해당 버전의 요청에는 30초 타임아웃이 있다. 로컬 CPython에서 실제 원본 학교 검색과 현재 주 시간표 조회를 각 1회 이상 성공했지만 이는 Workers 내부 실측이 아니다. 아래 master 브랜치에 대한 관찰과 구분한다.

## 판정

**보류.** Cloudflare Python Workers에서 upstream을 수정 없이 실조회할 수 있다는 증거가 없으며, 호환 실패라고 확정할 증거도 없다. 이 작업은 배포 금지 조건에 따라 로컬 스파이크와 문헌 조사를 수행한다. 무료 플랜 통과, 유료 전환, 관리형 CPython 대안 중 최종 선택은 아직 하지 않는다. 로컬 결과만으로 실제 Workers의 성능 또는 연결을 예측하지 않는다.

## 확인한 사실과 구분

| 항목 | 근거·결과 |
|---|---|
| 기획서 | `school-timetable-development-plan-v01.md`를 UTF-8로 읽었다. 요구사항은 수정 없는 upstream, 4082 통신, 변경 표시, 실환경 CPU·메모리·지연 및 장애 검사다. |
| 로컬 도구 | Windows, Python 3.13.14, Node v26.13.0, uv 0.12.7. 기본 환경에 pywrangler 실행 파일과 pycomcigan 패키지는 없다. |
| 패키지 | [upstream master의 메타데이터](https://raw.githubusercontent.com/hegelty/pycomcigan/master/pyproject.toml)는 1.4.2, requests, beautifulsoup4, urllib3를 명시한다. [PyPI](https://pypi.org/project/pycomcigan/) 최신 배포는 1.4.3이며 master와 동일하다고 가정하지 않는다. 이 실험은 소스 근거와 비교하기 위해 1.4.2를 지정했다. 배포 wheel과 master 소스의 동일성은 확인하지 않았다. |
| 통신 | 조사한 [upstream master helpers](https://raw.githubusercontent.com/hegelty/pycomcigan/master/pycomcigan/helpers.py)는 `http://comci.net:4082`와 동기 `requests.get`을 사용하며 해당 호출에 timeout 인수를 지정하지 않는다. 이 관찰을 1.4.2 wheel의 실측으로 취급하지 않는다. 원본은 평문 HTTP다. |
| 호환성 | [Cloudflare 패키지 문서](https://developers.cloudflare.com/workers/languages/python/packages/)는 pure Python, PyEmscripten, Pyodide 패키지 지원을 설명한다. wheel 형식만으로 네트워크 API 호환성까지 증명되지는 않는다. `requests`의 일반 동기 통신 경로가 Workers에서 동작하는지 실험이 필요하다. |
| 포트 | [Workers TCP 문서](https://developers.cloudflare.com/workers/runtime-apis/tcp-sockets/)는 별도의 `cloudflare:sockets` API 및 주소 제한을 설명한다. 4082가 명시적으로 금지된 포트라는 근거는 찾지 못했다. 이것은 `requests` 동작이나 해당 호스트 연결 성공을 뜻하지 않는다. HTTP fetch의 비표준 포트 경로도 별도 검증이 필요하다. |
| 자원 | [한도 문서](https://developers.cloudflare.com/workers/platform/limits/)의 무료 HTTP CPU 한도는 요청당 10ms, 메모리는 isolate당 128MB다. 네트워크 대기는 CPU 시간과 다르다. 로컬 import 벽시계 시간은 CPU와 메모리 수치가 아니다. |

## 검증 결과와 한계

로컬 스파이크의 설정과 코드가 제공되며, 실제 실행 결과는 아래 기록을 따른다. 원본 서버에 요청하지 않았으므로 4082 도달성, 403/429, 타임아웃 및 시간표·변경 표시 정확도는 **미측정**이다. 실제 Cloudflare CPU·메모리·콜드스타트·네트워크 왕복도 **미측정**이다. 로컬 계정 인증 상태는 확인하지 않았으며 인증정보를 수집하지 않았다. 패키지 설치에는 패키지 레지스트리 접근이, 실제 배포 환경 시험에는 별도로 Cloudflare 계정과 해당 Workers 권한이 필요하다.

## 후속 검증 계획

1. README의 로컬 런타임 import 실험을 수행하고 도구·의존성 lock 및 결과를 기록한다. import와 통신 성공을 구분한다.
2. 컴시간 이용 조건과 시험 대상 학교를 확인하고 요청 수·시간 제한을 정한 뒤 upstream 공개 API만 사용해 소량의 학교 검색과 시간표를 검사한다. 기존 호출에 timeout이 없으므로 별도 실행 프로세스의 시간 제한 등 중단 수단을 먼저 마련하고, 실패 시 자동 재시도하지 않는다. 403/429는 관찰 시 상태를 기록하고 중단한다. 원본 응답·학교 식별정보·자격정보는 기록하지 않는다.
3. 학교별 현재/다음 주 학생 시간표의 대표 교시와 `replaced` 의미를 허가된 기준 자료와 대조한다. 원본 값이 없으면 정확도는 미검증이다. 장애 사례는 가능한 범위에서 별도 격리 환경의 실패 주입으로 재현하며 실제 원본에 과도한 요청을 보내지 않는다.
4. 배포가 별도로 허용될 때만 Cloudflare 실제 환경에서 제한된 반복을 수행한다. 각 cold/warm 조건, 표본 수, 실패율, p50/p95 wall time, invocation CPU, isolate 메모리 및 1102 여부를 기록한다. 플랫폼 로그의 CPU와 로컬 벽시계를 분리한다. raw 데이터·시크릿은 로그에 남기지 않는다.
5. import, 통신, 파싱, 변경 표시, 403/429·타임아웃 처리와 반복 실측이 모두 충족되어야 후보 통과로 판정한다. 호환성은 있으나 10ms를 지속 초과하면 제한된 경계 최적화를 실측하고, 여전히 운영 기준에 미달하면 유료 Workers와 관리형 CPython의 비용·운영 부담을 비교한다.

## 로컬 실행 기록

- `uv sync`: 1.4.2 및 의존성 설치 성공. `workers-py` 1.17.9, `workers-runtime-sdk` 1.9.6, 실험용 uv 0.13.4, Wrangler 4.159.0. `uv.lock`과 pywrangler가 생성한 `pylock.toml`을 보존했다. npx Wrangler 버전은 별도로 고정되지 않았다.
- 최초 시도는 시스템 uv 0.12.7이 요구되는 0.13.4보다 오래되어 중단됐다. 실험 가상환경에 uv 0.13.4를 설치하고 Windows에서 `PYTHONUTF8=1`을 설정해 pywrangler의 cp949 디코딩 오류를 피했다. 도구가 Workers용 Pyodide Python 3.14.2를 별도로 받으면서 프로젝트의 CPython 3.13 조건과 다르다는 경고를 출력했다. 실행 성공이 양 환경의 동일성을 의미하지 않는다.
- 2026-11-10 호환 날짜는 로컬 Wrangler가 미래 날짜로 거부하여 2026-11-09로 고정했다. 가상환경을 번들에 넣지 않도록 진입점을 `src/`로 옮겼다.
- 로컬 서버 `127.0.0.1:8787`에서 첫 번째 시도 최초·후속 응답은 모두 HTTP 200, `import_ok`, `TimeTable_callable`, `get_school_code_callable` 모두 true였다. import 벽시계 시간은 각각 509ms와 0ms였다. 문서 명령으로 서버를 재시작해 최초 응답을 다시 확인한 결과 같은 세 값이 true, 779ms였다. 표본이 적고 타이머 분해능·캐시가 영향을 미치며, 서버 기동 시간과 실제 Cloudflare CPU 사용량은 포함하지 않는다.
- `worker.py` 구문 및 TOML 구문 검증 통과. 원본 서버 호출과 외부 Workers 배포는 하지 않았다.
