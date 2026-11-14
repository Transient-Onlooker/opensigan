# 개발 가이드

> 기준: 2026-11-14 `main`. 코드를 실행하거나 원본 서비스에 요청하기 전에 요청 범위를 확인하세요.

## 환경

- Python **3.13**, Node.js **22+**, Git
- Python 백엔드: `backend/`
- Svelte/Vite 프런트엔드: `frontend/`
- 독립적인 과거 Cloudflare 실험: `workers-api/`, `phase0/`, `phase0-mvp/`

### Windows PowerShell

저장소 루트에서:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
.\.venv\Scripts\python -m backend.app
```

다른 PowerShell:

```powershell
cd frontend
npm ci
npm run dev
```

`http://localhost:5173/opensigan/`은 일반적인 Vite 기본 주소이며, 실제 출력된 주소를 우선합니다. 프런트엔드 개발 프록시는 `/api`를 `127.0.0.1:8000`으로 전달합니다.

### Linux/macOS

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m backend.app
```

다른 터미널:

```bash
cd frontend
npm ci
npm run dev
```

이 설치는 `pycomcigan`의 고정 Git 커밋을 내려받는 등 네트워크·Git이 필요합니다. 패키지 설치를 제외한 **일반 단위 테스트는 실제 컴시간/NEIS 요청을 하지 않도록** 모킹되어 있습니다.

## 환경 변수

| 변수 | 용도 | 기본 동작 |
| --- | --- | --- |
| `NEIS_API_KEY` | NEIS 학교 검색·급식 조회 | 없으면 해당 API는 503 |
| `HOST` / `PORT` | Python API 리스닝 | `127.0.0.1` / `8000` |
| `ALLOWED_ORIGIN` | Python API의 허용 브라우저 Origin (쉼표 구분) | 미설정이면 CORS 허용 헤더 없음 |
| `OPENCIGAN_HISTORY_DB` | SQLite 이력 저장 파일 경로 | 미설정이면 이력 저장 비활성화 |
| `THREADS` | Waitress 스레드 수 | `8` |
| `VITE_API_BASE_URL` | 빌드된 프런트엔드의 API 출처 | 개발 중엔 동일 출처 `/api` 프록시 사용 |

`backend.app`은 `.env` 파일을 직접 파싱하지 않습니다. `.env.example`은 변수 이름을 알리기 위한 파일이므로, NEIS 키가 필요할 때만 실행 환경에 안전하게 주입하세요. `.env`, 실제 키, 원본 시간표 덤프, 학생 개인정보를 Git에 올리지 마세요.

변경 이력 저장은 원본 데이터 이용 조건을 확인하기 전 **실제 학교에서 활성화하지 마세요**. 합성 fixture만으로 검증할 수 있습니다.

## 테스트

저장소 루트에서 Python 단위·WSGI 테스트:

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```

과거 Worker 모듈 테스트:

```powershell
cd workers-api
..\.venv\Scripts\python -m unittest test_worker test_d1_cache test_migration -v
cd ..
```

프런트엔드와 LAN HTTP 통합 검사(의존성 설치 뒤):

```powershell
cd frontend
npm ci
npm run check
npm test
npm run build
cd ..
.\.venv\Scripts\python -m unittest discover -s tests/integration -v
```

Linux/macOS라면 Python 실행 경로를 `.venv/bin/python`으로 바꾸세요. CI는 `.github/workflows/ci.yml`에 기록된 순서로 이 검사를 수행합니다. 통과 사실은 GitHub Actions 결과로 확인하세요.

**실서비스를 호출하는 테스트는 별도:** `python -m tests.neis_sample_probe`와 `python -m tests.neis_local_probe`는 외부 요청을 보냅니다. `python -m backend.parser_health_probe`도 실제 컴시간 학교 검색을 수행합니다. 일상적인 변경·리뷰에서는 실행하지 않고 명시적인 확인이 필요할 때만 한 번 실행하세요.

## 개발 시 지켜야 할 계약

- `docs/openapi.yaml`을 API의 공개 계약 기준으로 유지합니다. 새/변경 엔드포인트는 `backend/app.py`, `frontend/src/api.ts`, OpenAPI 및 테스트를 함께 수정합니다.
- 주간 시간표는 **한국 시간 기준 이번 주·다음 주 월요일**을 받습니다. 급식은 최대 **7일** 구간을 받습니다.
- 원본 요청 수를 늘리지 말고 학교·기간 단위 캐시 및 single-flight를 우선합니다.
- 시간표 변경을 표시하는 `isChanged`와 **관측 이력**은 다릅니다. 과거 스냅샷 없이 변경 전 값을 추정하지 마세요.
- 오류 코드는 `error`, `code` 필드를 사용하며, 클라이언트에 내부 네트워크 정보·비밀키·예외 스택을 전달하지 않습니다.
- 네트워크·캐시 실패 시 빈 데이터로 덮어쓰지 않도록 기존 사용자 경험을 유지합니다.

## PR/리뷰 체크리스트

1. 기존 API 계약과 모바일·데스크톱 화면에 회귀가 없는지 확인한다.
2. 수정된 Python/TS 경로에 합성 데이터 기반 테스트를 추가한다.
3. 변경한 공개 필드·사용법·제약을 문서에 반영한다.
4. 실행하지 않은 검사는 '미실행'이라고 기록하고, 실측 조건과 날짜를 남긴다.
5. RPi의 SSH/Tailscale/방화벽·공개 터널·실제 데이터 저장 설정을 개발 변경과 묶어 임의로 적용하지 않는다.

이슈·기여 방식은 [CONTRIBUTING.md](../CONTRIBUTING.md)를 참조하세요.
