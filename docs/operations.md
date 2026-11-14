# 배포·운영·상태 모니터링

> **변경 범위:** 이 문서는 기존 구성의 확인·점검용입니다. 문서 갱신 자체로 터널, 방화벽 또는 서비스를 실행/수정하지 않습니다. RPi에서 실제 배포·재시작할 때는 기존 운영 상태를 먼저 확인하세요.

## 실행 경로 구분

| 환경 | 제공 내용 | 접근 및 상태 |
| --- | --- | --- |
| GitHub Pages | Svelte 정적 프런트엔드와 API 문서 | 페이지 빌드/배포 후 접근 가능. API 주소가 없으면 데이터 조회 불가 |
| RPi Python API | `backend.app` / Waitress | `127.0.0.1:8000` 로컬 바인딩 (원칙상 외부 포트 개방 없음) |
| RPi LAN preview | 정적 프런트엔드와 API, 개발 검수 | `LAN_HOST:8080/opensigan/`, 집 Wi-Fi로 제한하는 별도 서비스 |
| Cloudflare Workers/D1 | 초기 실험과 별도 코드 | `workers-api/`에 과거 배포 기록; 현재 Python API와 동일하다고 가정하지 않음 |

운영 파일: `deploy/opensigan.service`, `deploy/opensigan-preview.service`, `deploy/opensigan-preview-p0.conf`, `deploy/rpi-guard-opensigan.conf`. 서비스는 `systemd --user`에서 실행하도록 설계되어 있습니다. 자동 시작 여부와 실제 설치 상태는 RPi에서 따로 확인해야 합니다.

## 비밀키와 설정

- NEIS 키: `~/.config/opensigan/neis.env` (예: `NEIS_API_KEY=...`). 키 자체를 로그·Issue·PR에 붙이지 마세요.
- LAN 주소: `~/.config/opensigan/preview.env`의 `LAN_HOST`. 저장소에 실제 내부망 주소를 고정하지 마세요.
- 공개 CORS Origin: 서비스의 `ALLOWED_ORIGIN`. 실제 프런트엔드 출처와 정확히 맞추세요.
- 이력 저장: `OPENCIGAN_HISTORY_DB` 기본 미설정. 실제 데이터에 대한 수집·재제공 허용을 확인하기 전 활성화하지 마세요.
- GitHub Pages 배포: 저장소 변수 `API_BASE_URL`을 프런트엔드 빌드에서 `VITE_API_BASE_URL`로 전달합니다. 값이 없으면 Pages에 정적 화면만 표시될 수 있습니다.

## 비파괴적 점검 (RPi 내부)

```bash
systemctl --user status opensigan opensigan-preview --no-pager
curl --fail --silent --show-error http://127.0.0.1:8000/api/v1/status
journalctl --user -u opensigan-preview -n 30 --no-pager
```

`/api/v1/status`는 프로세스가 응답하는지만 확인하며 컴시간 또는 NEIS 상태를 보장하지 않습니다. 자세한 외부 API 점검은 [API 가이드](api-guide.md) 참조. 실제 학교 검색/시간표·급식 호출은 원본 서버에 트래픽을 발생시키므로 캐시/제한을 고려해 필요한 경우만 하세요.

## 상태 배지 및 GitHub Actions

| 배지 | 대상 | 통과의 의미 | 통과해도 확인되지 않는 것 |
| --- | --- | --- | --- |
| [CI](../.github/workflows/ci.yml) | `main` 및 PR의 `Check and deploy` | Python/Workers 테스트, Svelte/TS 검사, 빌드·배포 단계 | 실시간 컴시간/NEIS 원본 및 집 인터넷 안정성 |
| [Parser health](../.github/workflows/parser-health.yml) | `main`의 스케줄/수동 실행 | `대전` 학교 검색 한 번의 결과 형식/파싱 정상 | 전체 시간표 데이터 정확성, 모든 학교, 공개 API 가용성 |

**Parser health 일정:** `17 0 * * 1` (UTC) = 매주 월요일 **09:17 KST**. GitHub Actions의 예약 실행은 지연되거나 실행되지 않을 수 있으며, 워크플로가 아직 실행된 적 없으면 배지가 미확정일 수 있습니다. 동작은 `backend/parser_health_probe.py`에 정의돼 있으며 **하나의 검색 작업이 내부적으로 여러 HTTP 교환을 사용할 수 있습니다**. 재시도나 전체 시간표 조회를 하지 않습니다.

수동 검증은 GitHub 저장소 → **Actions → Parser health → Run workflow**에서 할 수 있습니다. 파서 검사 실패 시 즉시 원본 프로토콜 변경이라고 단정하지 말고, 설치·DNS/네트워크·원본 403/429·응답 스키마를 순서대로 구분하세요. 불필요한 재시도는 원본에 부담을 줍니다.

## 내부망 검수 및 되돌리기

- `opensigan-preview`는 `frontend/dist`를 제공하며, `LAN_HOST`가 없으면 시작하지 않습니다.
- P0 검수용 `deploy/opensigan-preview-p0.conf`는 `WorkingDirectory`를 `~/opensigan-releases/p0-20261114`로 지정하고 이력 DB 환경 변수를 비웁니다. 실제 적용 여부는 `systemctl --user cat opensigan-preview`로 확인하세요.
- 해당 P0 검수 drop-in을 되돌릴 때는, **실제로 설치된 파일 경로를 확인한 후** `.conf.disabled`로 이동하고 `systemctl --user daemon-reload`와 `systemctl --user restart opensigan-preview`를 실행합니다. 기존 `~/opensigan` 작업물은 삭제하지 않습니다.
- `rpi-guard-opensigan.conf`는 특정 LAN 대역·`wlan0`·8080 포트만 허용하도록 설계된 선택적 drop-in입니다. 이는 방화벽 재시작 때 적용되며, 파일을 제거해도 **이미 적용된 nftables 규칙이 즉시 사라지지는 않습니다**. 규칙 삭제 전 반드시 정확한 handle을 확인하세요.
- SSH, Tailscale, RPi 기본 방화벽, 다른 워처 서비스는 이 문서만 보고 변경하지 마세요. 외부 포트 개방과 Cloudflare Tunnel 설정은 별도 승인·검증 절차입니다.

## 자동 셔터와 통계

Pi 작업 폴더에만 있던 `backend/shutter.py`와 회귀 검증을 저장소에 통합했습니다. 프로세스별 기본 임계치는 60초에 600요청 또는 1분 load average 8이며, 초과 시 30초 동안 `503 service_overloaded`와 `Retry-After`를 반환합니다. `SHUTTER_MAX_REQUESTS`, `SHUTTER_WINDOW_SECONDS`, `SHUTTER_COOLDOWN_SECONDS`, `SHUTTER_MAX_LOAD`로 조절합니다. 요청량·부하 조건은 각각 0이면 비활성화되며, load average가 없는 OS에서는 부하 조건을 적용하지 않습니다. 상태 확인과 인증을 요구하는 관리자 통계는 셔터 중에도 조회할 수 있습니다. OPTIONS는 셔터에 포함되지 않습니다. 프로세스별 제한이므로 전체 서비스 합산 제한은 아닙니다.

통계 설정과 운영 지표의 의미는 [이용 통계](analytics.md)를 참고하세요. 내부망 서버는 최신 `/assets/...` 경로와 기존 `/opensigan/assets/...` 경로를 모두 제공합니다.

### 배포 검증

이용 통계와 후속 UI를 별도 릴리스로 배치하고 기존 작업 폴더를 보존했습니다. UI 변경 시 검수 서비스만 전환해 API 캐시를 유지했습니다. 서버에서 Python 회귀 검증과 관리자 인증을 확인했고, GitHub 검사 및 Pages 배포도 성공했습니다. 공개 사이트의 새 UI 자산과 외부 관리자 인증·CORS 응답을 HTTP로 검증했습니다. GUI 브라우저·모바일 실기기 시각 검증은 수행하지 않았습니다. 상세 서버 위치·백업 경로·운영 메타데이터는 공개 문서에 포함하지 않습니다.

## 공개 전 체크리스트

- [ ] 원본 컴시간 데이터의 이용 조건·저장·재제공 범위 확인
- [ ] 프록시/Tunnel 뒤 실제 클라이언트 식별과 60회/60초 요청 제한의 상호작용 검증
- [ ] LAN과 외부 접속에서 캐시 HIT/MISS 및 오류 상황 실측
- [ ] CORS·보안 헤더·API 버전·오류 계약·비밀키 보호 확인
- [ ] RPi Wi-Fi/정전·업데이트·백업·되돌리기 절차 확보
- [ ] 공개 배포 여부에 대한 사용자 별도 승인

[지연 계측 자료](latency-2026-11-13.md) · [개발 가이드](development.md)
