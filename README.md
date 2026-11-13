# Opencigan

[![CI](https://github.com/Transient-Onlooker/opensigan/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Transient-Onlooker/opensigan/actions/workflows/ci.yml)
[![Parser health](https://github.com/Transient-Onlooker/opensigan/actions/workflows/parser-health.yml/badge.svg?branch=main)](https://github.com/Transient-Onlooker/opensigan/actions/workflows/parser-health.yml)

**학교 시간표와 급식을 한곳에서 조회하는 웹서비스**입니다. 컴시간 시간표와 NEIS 급식을 사용하며, 프런트엔드는 Svelte, 주 백엔드는 Python입니다.

[웹사이트](https://opencigan.mcv.kr) · [API 명세](docs/openapi.yaml) · [기능 로드맵](docs/roadmap.md)

> **현재 상태 (2026-11-14):** 주 주소는 [opencigan.mcv.kr](https://opencigan.mcv.kr)입니다. 웹사이트는 Raspberry Pi 백엔드(Tailscale Funnel 경유)에 연결되어 시간표/급식 조회가 동작합니다. 외부 개발자용 API의 공개 운영은 별도 검증·승인이 필요합니다.

## 구현된 기능

- 학교 검색, 학년·반 선택, 선택 정보 브라우저 저장
- 오늘의 시간표, 우리 반 주간 시간표, 학년 전체 반별 비교, 교사별 시간표 검색
- 교시별 변경 표시, 원본 갱신/수집 시각, 실패 시 가능한 범위에서 이전 캐시 표시
- NEIS 학교 매칭 및 조식·중식·석식 조회, 날짜 이동
- 반응형 모바일 화면, 다크 모드
- 읽기 전용 `/api/v1` JSON 엔드포인트 6개(상태·학교 검색 2종·시간표·급식·변경 이력) 및 OpenAPI 3.1 명세
- 변경 이력 비교/페이지네이션 코드: **저장은 기본 비활성화**이며 첫 수집분은 비교 기준으로만 사용

## 시작하기

요구사항: **Python 3.13**, **Node.js 22 이상**. 명령은 저장소 루트 기준입니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
.\.venv\Scripts\python -m backend.app
```

별도 터미널에서:

```powershell
cd frontend
npm ci
npm run dev
```

Vite가 표시하는 로컬 주소의 `/opensigan/`을 엽니다. 개발 서버의 `/api` 요청은 `http://127.0.0.1:8000`으로 프록시됩니다. 시간표 검색은 NEIS 키 없이도 동작하지만, **NEIS 학교·급식 조회에는 서버 측 `NEIS_API_KEY`가 필요**합니다. `.env.example`은 예시이고 `backend.app`은 `.env`를 자동으로 읽지 않으므로 실행 환경에 키를 별도로 설정해야 합니다. 키를 코드·커밋·브라우저 번들에 포함하지 마세요.

전체 로컬 설정과 테스트: [개발 가이드](docs/development.md).

## 문서

| 문서 | 내용 |
| --- | --- |
| [개발 가이드](docs/development.md) | 개발환경, 오프라인 테스트, PR 체크리스트 |
| [구조 설명](docs/architecture.md) | 프런트엔드·Python API·캐시·이력 흐름 |
| [API 사용 가이드](docs/api-guide.md) | 엔드포인트, 응답 예시, 오류·캐시 의미 |
| [OpenAPI 3.1](docs/openapi.yaml) | 기계 판독 가능한 계약 |
| [운영·모니터링](docs/operations.md) | LAN 검수, RPi 서비스, 배지, 복구 절차 |
| [개발 로드맵](docs/roadmap.md) | P0~P4 구현 현황 및 후속 작업 |
| [지연 계측](docs/latency-2026-11-13.md) | 실제 내부망 샘플 및 측정 범위 |
| [기여 가이드](CONTRIBUTING.md) | 이슈·PR·보안·검증 기준 |

API Playground는 **API와 같은 출처로 제공하는 내부망 검수 사이트**의 `/api-docs.html`에 있습니다. GitHub Pages에서는 상대 경로 API가 없으므로 실시간 요청 기능이 비활성화됩니다.

## 상태 배지의 의미

- **CI:** 저장소 테스트·Svelte/TypeScript 검사·빌드/배포 워크플로 상태입니다. 원본 컴시간 서버의 실시간 가용성은 측정하지 않습니다.
- **Parser health:** 매주 월요일 **09:17 KST**에 `대전` 학교 검색을 **한 차례** 수행해 현재 검색 프로토콜·복호화·결과 형식을 검사합니다. 수동 실행도 가능합니다. 시간표 전체 조회나 API 서비스 가동 여부를 검사하지 않으며, 원본 서버나 Actions 네트워크 장애 때문에 실패할 수 있습니다. 첫 실행 전에는 배지가 미확정 상태일 수 있습니다.

자세한 해석 및 장애 대응: [운영·모니터링](docs/operations.md).

## 공개 운영 전 주의사항

- Python API는 현재 `127.0.0.1:8000`에 바인딩하는 구성입니다. 내부망 검수 서버는 별도로 운영하며, 공개 터널 설정은 이 저장소의 문서 갱신으로 변경되지 않습니다.
- 메모리 캐시는 **프로세스별**이고 기본 TTL은 30분입니다. 변경 이력 SQLite 저장은 기본 비활성화입니다.
- 호출 제한은 프로세스의 `REMOTE_ADDR`를 기준으로 합니다. Cloudflare 같은 역방향 프록시 뒤에서는 실제 이용자를 구별하지 못할 수 있어 공개 전 별도 구성이 필요합니다.
- 컴시간 원본의 재제공·저장 허용 범위와 외부 서비스 이용 조건을 확인하기 전에는 공개 API를 활성화하지 않습니다. 외부 제공 데이터가 정상 조회된다는 사실이 재배포 허가를 뜻하지는 않습니다.
- 과거 Cloudflare Workers/D1 실험은 [별도 기록](workers-api/README.md)에 남아 있습니다. [초기 설계](school-timetable-development-plan-v01.md)는 현재 구현의 기준 문서가 아닙니다.
- **라이선스:** 저장소에 별도의 `LICENSE` 파일은 아직 없습니다. 공개 저장소라는 사실만으로 외부 사용·재배포 권한이 부여되지는 않습니다.
