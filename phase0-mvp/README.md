# MVP 고정 버전의 Workers 로컬 실험

2026-11-10: `pycomcigan`을 MVP와 같은 Git 커밋 `e8ceaec7bad47cef946ec0174cc523f3652f42ee`로 고정하고 Python Workers 패키지 준비를 시도했다. Python 3.13.14, uv 0.13.4, pywrangler 1.17.9 및 Wrangler를 사용했다.

`pywrangler dev --local`은 Workers용 CPython 3.14.2 Emscripten 의존성을 `uv pip compile --no-build`로 해석하는 단계에서 실패했다. 출력은 Git 의존성 `pycomcigan`의 소스 배포본 빌드가 금지됐다고 보고했다. 검색 API는 호출되지 않았다. 이 결과는 현재 Git 의존성 설치 방식의 문제이며, 사전 빌드 wheel 사용 시 통신·CPU 호환성 여부는 알려주지 않는다.

`run_local.py`는 재현용 실험이며 로컬 서버 준비 후 원본 검색 API를 최대 1회 호출한다. 해당 호출은 내부적으로 여러 HTTP 요청을 할 수 있다. 결과에는 성공 여부, 건수, 시간과 예외 종류만 기록한다. 원본 이용조건 확인 후 실행하고 반복 호출하지 않는다. 실환경 Workers CPU·네트워크와 공개 서비스 적합성은 여전히 미검증이다.
