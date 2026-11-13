# Opencigan

컴시간의 학생 시간표와 NEIS 급식을 조회하는 서비스입니다. 화면은 GitHub Pages에서 배포하고, API는 라즈베리 파이에서 운영합니다. API 공개 전에는 같은 집 Wi-Fi에 연결한 기기에서 라즈베리 파이의 검수 페이지를 이용합니다.

현재 개발 방향은 [기능 로드맵](docs/roadmap.md)을 참고하세요. `school-timetable-development-plan-v01.md`는 초기 설계 기록이며 현재 배포 구조의 기준이 아닙니다.

## 로컬 실행

Python 3.13과 Node.js 22 이상이 필요합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
$env:NEIS_API_KEY = (Get-Content -Encoding UTF8 .env | Where-Object { $_ -match '^NEIS_API_KEY=' } | Select-Object -First 1) -replace '^NEIS_API_KEY=', ''
.\.venv\Scripts\python -m backend.app
```

프로젝트 루트의 `.env.example`을 `.env`로 복사하고 `NEIS_API_KEY=발급받은키` 형식으로 입력합니다. `.env`는 Git에서 제외되며 위 명령으로 로컬 서버를 시작할 때 읽습니다.

다른 터미널에서 다음을 실행합니다.

```powershell
cd frontend
npm ci
npm run dev
```

Vite가 출력하는 로컬 주소를 열면 `/api` 요청을 로컬 API로 전달합니다. 인증키가 없으면 시간표는 조회할 수 있지만 NEIS 학교 및 급식 조회는 실패합니다. 인증키를 코드나 Git에 넣지 마세요. 급식 학교는 동명이교를 구별할 수 있도록 주소를 확인하고 직접 선택해야 합니다.

## 검증

실제 집 Wi-Fi 사용자 테스트의 요청별 처리 시간은 [2026-11-13 계측 기록](docs/latency-2026-11-13.md)에 정리했습니다. 서버 처리 시간과 화면이 표시되기까지의 전체 시간은 구분합니다.

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
cd frontend
npm run check
npm test
npm run build
```

네트워크를 사용하는 별도 확인으로 `python -m tests.neis_sample_probe`를 실행할 수 있습니다. NEIS 인증키 없는 공식 샘플을 이용해 특정 학교의 2026-11-09 식단을 확인합니다. 2026-11-10에 학교 1곳과 급식 2건의 파싱을 확인했습니다. 샘플은 최대 5건만 제공하므로 정식 인증키와 전체 페이지 조회의 대체 검증이 아닙니다. 과거 식단이 제거되면 이 확인도 실패할 수 있습니다.

실제 인증키를 사용하는 로컬 통합 검증은 프로젝트 루트의 `.env`에 `NEIS_API_KEY=발급받은키` 한 줄을 설정한 뒤, 학교 검색 결과가 정확히 하나인 이름으로 수동 실행합니다.

```powershell
.\.venv\Scripts\python -m tests.neis_local_probe "학교 이름" 2026-11-09
```

날짜는 생략하면 오늘이며, 급식이 없는 날에는 0건이 정상일 수 있습니다. 스크립트는 `.env`의 키를 메모리에서 읽고 임시 로컬 HTTP 서버를 통해 학교와 하루 급식을 조회합니다. 각 HTTP 상태와 결과 건수만 출력하며, 학교 검색이 유일하지 않거나 조회가 실패하면 중단합니다. 키를 명령 인자에 넣지 마세요. 이 명령은 실제 NEIS에 네트워크 요청을 보내며 일반 오프라인 테스트에는 포함되지 않습니다.

## 배포 현황과 제한

- GitHub Actions는 저장소 변수 `API_BASE_URL`에 지정된 파이의 HTTPS 주소를 Pages 빌드에 사용합니다. 공개 터널이 닫혀 있으면 Pages 화면은 열리지만 데이터는 조회할 수 없습니다.
- 파이의 [API 서비스](deploy/opensigan.service)는 `127.0.0.1:8000`에서 실행합니다. [집 Wi-Fi 검수 서비스](deploy/opensigan-preview.service)는 `~/.config/opensigan/preview.env`에 지정한 `LAN_HOST`의 8080 포트에서, API 주소를 비운 채 빌드한 `frontend/dist`와 API를 함께 제공합니다. 두 서비스는 `~/.config/opensigan/neis.env`에서 키를 읽습니다. 부팅 시 자동 시작에는 사용자 lingering이 필요합니다.
- 현재 P0 내부 검수는 [전용 drop-in](deploy/opensigan-preview-p0.conf)으로 `~/opensigan-releases/p0-20261114`의 별도 빌드를 사용하며 기존 `~/opensigan` 작업 내용은 보존합니다. 되돌릴 때 해당 drop-in을 `.conf.disabled`로 옮기고 `systemctl --user daemon-reload` 및 `systemctl --user restart opensigan-preview`를 실행합니다.
- 집 Wi-Fi에서 `http://<LAN_HOST>:8080/opensigan/`을 열어 검수합니다. 파이에서 `curl -f "http://<LAN_HOST>:8080/api/v1/status"`로 검수 서비스의 API 응답을 따로 확인할 수 있습니다.
- 파이에 `rpi-guard.service`가 있으면 UFW 비활성 여부와 별개로 내부망 8080이 차단될 수 있습니다. [전용 drop-in](deploy/rpi-guard-opensigan.conf)은 기존 방화벽 파일을 수정하지 않고, 방화벽 시작 직후 `wlan0`의 `172.30.1.0/24`에서 들어오는 TCP 8080만 허용합니다. 아래 명령은 다음 방화벽 시작부터 적용하며 실행 중인 방화벽을 재시작하지 않습니다. 영구 적용을 되돌리려면 설치한 파일을 `.conf.disabled`로 옮기고 `sudo systemctl daemon-reload`를 실행합니다. 현재 활성 규칙은 별도로 남아 있으므로 즉시 철회할 때는 `sudo nft -a list chain inet rpi_guard input`에서 해당 규칙의 handle을 확인해 그 규칙만 삭제합니다.

  ```bash
  sudo install -D -m 644 ~/opensigan/deploy/rpi-guard-opensigan.conf /etc/systemd/system/rpi-guard.service.d/opensigan-lan.conf
  sudo systemctl daemon-reload
  ```
- 파이 API는 Waitress와 프로세스 내 메모리 캐시를 사용합니다. 집 Wi-Fi 검수 서비스는 별도로 실행하며 공개망에 노출하지 않습니다.
- API 명세는 [OpenAPI 3.1](docs/openapi.yaml), 내부망 Playground는 `/opensigan/api-docs.html`에서 확인합니다. 각 프로세스의 클라이언트 주소당 데이터 요청은 분당 60회로 제한하며 프록시 뒤의 클라이언트 식별은 공개 전에 검증해야 합니다.
- 변경 이력은 기본 비활성화되어 있습니다. 원본 이용 조건 확인 전에는 실제 학교 데이터를 저장하지 마세요. 허용된 합성 데이터 검증 시에만 `OPENCIGAN_HISTORY_DB`를 로컬 SQLite 경로로 설정할 수 있으며 30일 관측 이력을 보존합니다.
- 컴시간 원본 데이터의 재제공 허용 범위, 개인정보 처리, 외부 서비스 이용 조건은 공개 전에 확인해야 합니다. 교사 정보는 upstream이 제공한 범위로 표시합니다.
- Cloudflare Worker/D1은 [기존 배포 기록](workers-api/README.md)과 [Phase 0 실험](phase0/REPORT.md)에 남겨 두었습니다.
- 실제 NEIS API 확인에는 서버 측 인증키가 필요합니다. API 키를 브라우저 번들에 포함하지 않습니다.
