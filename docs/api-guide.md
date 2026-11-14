# Opencigan API 가이드

> **상태:** 로컬·내부망 검수용 Python API 계약을 설명합니다. 공개 개발자용 API 서비스의 가용성이나 제3자 재제공 허용을 의미하지 않습니다. 형식의 기준은 [OpenAPI 3.1](openapi.yaml)입니다.

## 호출 기본

- 기본 경로: `/api/v1`
- 메서드: `GET`, `HEAD`, `OPTIONS` (쓰기 API 없음)
- 개발용 API 주소: `http://127.0.0.1:8000` (API를 실행하는 **같은 기기**에서만 접근)
- HTTP 응답: JSON (UTF-8), 시간표 구독만 `text/calendar` (UTF-8). 구독 피드는 비공유 캐시에서 재검증할 수 있으며, 나머지는 `Cache-Control: no-store`를 사용합니다.
- 브라우저에서 다른 출처로 호출하려면 서버의 `ALLOWED_ORIGIN`과 배포 경로를 함께 맞춰야 합니다.

API와 같은 출처의 LAN 검수 화면은 `/opensigan/api-docs.html`에 요청 Playground가 있습니다. GitHub Pages에서 이 Playground의 실시간 요청은 비활성화되어 있습니다.

## 엔드포인트

| 메서드 | 경로 | 필수 쿼리 | 주의 |
| --- | --- | --- | --- |
| GET | `/api/v1/status` | 없음 | 프로세스 생존 확인. 원본 서버 검사 아님 |
| GET | `/api/v1/schools` | `q` | 컴시간 학교 검색, 검색어 1~50자 |
| GET | `/api/v1/neis/schools` | `q` | NEIS 학교 검색, 서버 측 API 키 필요 |
| GET | `/api/v1/timetable` | `school`, `week` | 컴시간 학교 ID와 이번/다음 주 월요일(KST) |
| GET | `/api/v1/timetable.ics` | `school`, `grade`, `class` | 지속해서 사용하는 iCalendar 구독 URL, 기본 이번 주·`weeks=2`면 다음 주까지 |
| GET | `/api/v1/meals` | `school`, `from`, `to` | NEIS 학교 ID와 최대 7일(양 끝 포함) |
| GET | `/api/v1/timetable/history` | `school`, `week` | 선택적 `cursor`. 변경 이력 미설정 시 503 |

### 학교 ID는 출처별로 다릅니다

- 컴시간: `학교코드:학교명` (예시: `1234:예시학교`)
- NEIS: `시도교육청코드:학교코드` (예시: `B10:1234567`)

한쪽 ID를 다른 엔드포인트에 넘기지 마세요. 사용자 화면에서는 컴시간 학교를 선택한 뒤 NEIS 학교를 별도로 검색·확인합니다.

### 예제: 로컬 시간표 조회

```bash
# 합성 ID이며 실제 서버에서 유효한 학교라는 뜻이 아닙니다.
curl --get 'http://127.0.0.1:8000/api/v1/timetable' \
  --data-urlencode 'school=1234:예시학교' \
  --data-urlencode 'week=2026-11-16'
```

이 예제의 날짜는 **2026-11-14 기준 다음 주 월요일**입니다. API는 호출 시점에 해당하는 이번/다음 주만 허용하므로 다른 날짜에는 `week`를 바꿔야 합니다. 먼저 `/api/v1/schools`에서 얻은 **실제 학교 ID**를 사용하세요.

응답 필드의 형태(아래는 합성 데이터):

```json
{
  "schoolId": "1234:예시학교",
  "weekStart": "2026-11-16",
  "records": [
    {
      "grade": 2, "class": 3, "date": "2026-11-16",
      "period": 1, "subject": "수학", "teacher": "예시교사",
      "isChanged": false
    }
  ],
  "sourceUpdatedAt": "2026-11-13T18:00:00+09:00",
  "fetchedAt": "2026-11-14T00:00:00+00:00",
  "stale": false,
  "cacheStatus": "miss"
}
```

기본 `records`는 요청한 학교의 **전체 학급**을 포함합니다. 특정 반만 원하면 `grade=2&class=3`, 교사 이름 일부로 검색하려면 `teacher=김`을 추가할 수 있습니다. 필터 요청은 학교·주별 서버 캐시를 재사용하므로 원본 요청이 늘지 않습니다.

### 시간표 캘린더 구독 (.ics)

웹 화면의 **캘린더 구독 링크**를 눌러 URL을 복사한 뒤, 캘린더 앱에 URL 구독으로 등록할 수 있습니다. 시간이 지나도 같은 URL이 현재 주를 가리키며 `weeks=2`를 선택하면 다음 주까지 포함합니다. 구독 요청도 JSON 시간표와 같은 서버 캐시를 이용합니다.

```bash
curl --get 'http://127.0.0.1:8000/api/v1/timetable.ics' \
  --data-urlencode 'school=1234:예시학교' \
  --data-urlencode 'grade=2' \
  --data-urlencode 'class=3' \
  --data-urlencode 'weeks=2'
```

기본값 `mode=periods`는 수업마다 종일 일정을 만들고, `mode=summary`는 하루 수업을 종일 일정 하나로 묶습니다. 원본에는 실제 교시 시각이 없습니다. 응답의 `ETag`를 다음 요청의 `If-None-Match`로 보내면 피드가 같을 때 본문 없이 `304`로 응답합니다. 앱마다 갱신 주기가 다르며, 구독 주소는 캘린더 앱에서 접근할 수 있어야 합니다.

## 캐시와 변경 이력

- `cacheStatus`: `hit`(신선한 캐시), `miss`(새로 가져옴), `stale`(원본 갱신 실패 등으로 이전 값 제공). **시간표에만 포함**됩니다.
- `stale`: 최신 값임을 보장할 수 없는 응답 표시. 검색·급식 등에도 사용됩니다.
- `sourceUpdatedAt`: 원본이 제공한 갱신 시각. 없으면 `null`.
- `fetchedAt`: 이 백엔드가 데이터를 수집한 시각. **사용자의 요청 시각과 다를 수 있습니다**.
- `isChanged`: 컴시간이 표시한 수업 변경 여부. 변경 이력 엔드포인트의 before/after와 구분됩니다.

이력 API는 `OPENCIGAN_HISTORY_DB`로 명시적으로 활성화된 경우에만 동작합니다. 최초 관측은 기준 데이터만 만들고, 이후 관측한 차이를 `added`/`deleted`/`changed`로 제공합니다. 응답의 `nextCursor`가 있다면 그대로 `cursor`에 넘깁니다. 관측 이력 보존 기간은 최대 30일입니다.

## 오류 및 호출 정책

| HTTP | `code` | 의미 |
| --- | --- | --- |
| 400 | `invalid_request` | 쿼리 누락/형식 오류 |
| 404 | `not_found` | 지원하지 않는 경로 |
| 405 | `method_not_allowed` | 지원하지 않는 메서드 |
| 429 | `rate_limited` | 현재 프로세스 기준 호출 제한; `Retry-After` 사용 |
| 503 | `history_disabled` | 변경 이력 저장 비활성화 |
| 503 | `upstream_unavailable` | 원본/키/기타 조회 실패 |

응답 오류에는 `error`(메시지)와 `code`(식별자)가 포함됩니다. Python API의 요청 제한은 **프로세스별 `REMOTE_ADDR`당 60회/60초**이며 `status` 조회는 제외됩니다. 역방향 프록시 뒤에서는 여러 사용자가 같은 IP로 인식될 수 있으므로 이 설정을 그대로 인터넷에 공개하지 마세요. 실패 시 과도한 동시 재시도 대신 `Retry-After`와 백오프를 지키세요.

**공개 API 정책:** CORS 허용은 브라우저의 출처 제한일 뿐 인증이나 원본 데이터 재배포 권한의 대체가 아닙니다. 이용 약관·데이터 권리·악용 방지·프록시 뒤 IP 식별을 검토한 후 별도로 활성화해야 합니다.

[구현 구조](architecture.md) · [운영 가이드](operations.md)
