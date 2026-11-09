# 오픈시간표

컴시간의 학생 시간표와 NEIS 급식을 조회하는 로컬 MVP입니다. GitHub Pages는 정적 화면만 제공하며 별도의 HTTPS API 서버와 `API_BASE_URL` 저장소 변수가 있어야 실제 조회가 가능합니다. 현재 API는 로컬 개발용이며 공개 운영 구성으로 검증되지 않았습니다.

## 로컬 실행

Python 3.13과 Node.js 22 이상이 필요합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
$env:NEIS_API_KEY = '<NEIS 인증키>'
.\.venv\Scripts\python -m backend.app
```

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

## 배포 현황과 제한

- Pages는 GitHub Actions로 빌드·배포합니다. GitHub 저장소 변수 `API_BASE_URL`에 별도로 운영되는 HTTPS API 주소가 없으면 화면에 연결 안내가 표시됩니다.
- API는 단일 프로세스 메모리 캐시를 사용합니다. D1, 다중 인스턴스 간 잠금, 영구 캐시, 전역 속도 제한, 운영 모니터링은 아직 없습니다. 개발용 HTTP 서버를 그대로 공개하면 안 됩니다.
- 컴시간 원본 데이터의 재제공 허용 범위, 개인정보 처리, 외부 서비스 이용 조건은 공개 전에 확인해야 합니다. 교사 정보는 upstream이 제공한 범위로 표시합니다.
- Python Workers의 실제 실행 적합성과 CPU 한도 판정은 미완료입니다. [Phase 0 보고서](phase0/REPORT.md)를 참고하세요. 현재 CPython 구현은 로컬 검증용이며 최종 호스팅 결정을 뜻하지 않습니다.
- 실제 NEIS API 확인에는 서버 측 인증키가 필요합니다. API 키를 브라우저 번들에 포함하지 않습니다.
