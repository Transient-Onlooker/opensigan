# 오픈시간표

컴시간의 학생 시간표와 NEIS 급식을 조회하는 MVP입니다. GitHub Pages는 정적 화면을 제공하고 Cloudflare Worker가 API를 처리합니다. 실제 Worker에서 학교 검색과 시간표 조회를 각각 한 번 확인했으며, 운영 안정성과 데이터 이용 조건은 계속 검증해야 합니다.

운영 Worker에서 인증된 NEIS 학교 검색과 주간 급식 조회가 성공했습니다. 이 확인은 단일 학교 기준이며 운영 안정성은 계속 검증해야 합니다.

## 로컬 실행

Python 3.13과 Node.js 22 이상이 필요합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
$env:NEIS_API_KEY = (Get-Content -Encoding UTF8 .env | Where-Object { $_ -match '^NEIS_API_KEY=' } | Select-Object -First 1) -replace '^NEIS_API_KEY=', ''
.\.venv\Scripts\python -m backend.app
```

프로젝트 루트의 `.env.example`을 `.env`로 복사하고 `NEIS_API_KEY=발급받은키` 형식으로 입력합니다. `.env`는 Git에서 제외되며 위 명령으로 로컬 서버를 시작할 때 읽습니다. 운영 Workers에는 별도의 서버 측 Secret을 설정해야 합니다.

다른 터미널에서 다음을 실행합니다.

```powershell
cd frontend
npm ci
npm run dev
```

Vite가 출력하는 로컬 주소를 열면 `/api` 요청을 로컬 API로 전달합니다. 인증키가 없으면 시간표는 조회할 수 있지만 NEIS 학교 및 급식 조회는 실패합니다. 인증키를 코드나 Git에 넣지 마세요. 급식 학교는 동명이교를 구별할 수 있도록 주소를 확인하고 직접 선택해야 합니다.

## 검증

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
cd frontend
npm run check
npm run build
```

네트워크를 사용하는 별도 확인으로 `python -m tests.neis_sample_probe`를 실행할 수 있습니다. NEIS 인증키 없는 공식 샘플을 이용해 특정 학교의 2026-11-09 식단을 확인합니다. 2026-11-10에 학교 1곳과 급식 2건의 파싱을 확인했습니다. 샘플은 최대 5건만 제공하므로 정식 인증키와 전체 페이지 조회의 대체 검증이 아닙니다. 과거 식단이 제거되면 이 확인도 실패할 수 있습니다.

실제 인증키를 사용하는 로컬 통합 검증은 프로젝트 루트의 `.env`에 `NEIS_API_KEY=발급받은키` 한 줄을 설정한 뒤, 학교 검색 결과가 정확히 하나인 이름으로 수동 실행합니다.

```powershell
.\.venv\Scripts\python -m tests.neis_local_probe "학교 이름" 2026-11-09
```

날짜는 생략하면 오늘이며, 급식이 없는 날에는 0건이 정상일 수 있습니다. 스크립트는 `.env`의 키를 메모리에서 읽고 임시 로컬 HTTP 서버를 통해 학교와 하루 급식을 조회합니다. 각 HTTP 상태와 결과 건수만 출력하며, 학교 검색이 유일하지 않거나 조회가 실패하면 중단합니다. 키를 명령 인자에 넣지 마세요. 이 명령은 실제 NEIS에 네트워크 요청을 보내며 일반 오프라인 테스트에는 포함되지 않습니다.

## 배포 현황과 제한

- Pages는 GitHub Actions로 빌드·배포하며 저장소 변수 `API_BASE_URL`로 Worker 주소를 지정합니다. Worker 배포와 NEIS Secret 설정은 [Workers 안내](workers-api/README.md)를 따릅니다.
- 로컬 API는 단일 프로세스 메모리 캐시를 사용하고, 배포된 Worker는 D1 캐시와 원본별 갱신 제한을 사용합니다. 분산 환경의 동시성, 운영 모니터링과 반복 안정성은 아직 검증되지 않았습니다. 개발용 HTTP 서버를 그대로 공개하면 안 됩니다.
- 컴시간 원본 데이터의 재제공 허용 범위, 개인정보 처리, 외부 서비스 이용 조건은 공개 전에 확인해야 합니다. 교사 정보는 upstream이 제공한 범위로 표시합니다.
- Python Workers의 무료 CPU 한도와 반복 실행 적합성 판정은 미완료입니다. 기존 실험은 [Phase 0 보고서](phase0/REPORT.md)를 참고하세요.
- 실제 NEIS API 확인에는 서버 측 인증키가 필요합니다. API 키를 브라우저 번들에 포함하지 않습니다.
