from datetime import date, datetime, timedelta, timezone
import threading
import time

_protocol = None
_protocol_expires = 0.0
_protocol_lock = threading.Lock()


def _search_with_cached_protocol(query, *, retry=True):
    from pycomcigan.helpers import get_comcigan_response_for_codes, school_search
    from pycomcigan.service_page import decode_service_page
    from pycomcigan.service_protocol import parse_service_protocol

    global _protocol, _protocol_expires
    with _protocol_lock:
        now = time.monotonic()
        reused = _protocol is not None and now < _protocol_expires
        if not reused:
            _protocol = parse_service_protocol(decode_service_page(get_comcigan_response_for_codes().text))
            _protocol_expires = time.monotonic() + 300
        protocol = _protocol
    try:
        return school_search(query, protocol.endpoint, protocol)
    except RuntimeError as exc:
        message = str(exc)
        invalid_protocol = message in (
            'Encrypted response protocol mismatch',
            'Encrypted response authentication failed',
        )
        rejected = 'HTTP 403' in message
        if invalid_protocol or rejected:
            with _protocol_lock:
                if _protocol is protocol:
                    _protocol = None
                    _protocol_expires = 0.0
        if invalid_protocol and reused and retry:
            return _search_with_cached_protocol(query, retry=False)
        raise


def search_schools(query):
    schools = []
    for row in _search_with_cached_protocol(query):
        if (not isinstance(row, (list, tuple)) or len(row) < 4
                or not isinstance(row[3], int) or isinstance(row[3], bool) or row[3] <= 0
                or not isinstance(row[2], str) or not row[2] or len(row[2]) > 50
                or ":" in row[2] or not isinstance(row[1], str)):
            raise RuntimeError("학교 검색 응답 형식이 올바르지 않습니다")
        schools.append({"id": f"{row[3]}:{row[2]}", "name": row[2], "region": row[1]})
    return schools


def validate_timetable_week(week):
    if not isinstance(week, str):
        raise ValueError("주 시작일이 올바르지 않습니다")
    try:
        start = date.fromisoformat(week)
    except ValueError:
        raise ValueError("주 시작일이 올바르지 않습니다") from None
    if start.isoformat() != week:
        raise ValueError("주 시작일이 올바르지 않습니다")
    today = datetime.now(timezone(timedelta(hours=9))).date()
    current = today - timedelta(days=today.weekday())
    offset = (start - current).days // 7
    if start.weekday() != 0 or offset not in (0, 1):
        raise ValueError("현재 주 또는 다음 주의 월요일을 선택하세요")
    return offset


def fetch_timetable(school_id, week):
    from pycomcigan import TimeTable

    if not isinstance(school_id, str):
        raise ValueError("학교 식별자가 올바르지 않습니다")
    parts = school_id.split(":")
    if (len(parts) != 2 or not parts[0].isascii() or not parts[0].isdigit()
            or not parts[1] or len(parts[1]) > 50):
        raise ValueError("학교 식별자가 올바르지 않습니다")
    code, name = parts
    if int(code) == 0:
        raise ValueError("학교 식별자가 올바르지 않습니다")
    offset = validate_timetable_week(week)
    start = date.fromisoformat(week)
    try:
        timetable = TimeTable(name, school_code=int(code), week_num=offset)
    except ValueError as exc:
        raise RuntimeError("시간표 제공자의 응답이 올바르지 않습니다") from exc
    records = []
    data = timetable.timetable
    if not isinstance(data, (list, tuple)) or len(data) > 20:
        raise RuntimeError("시간표 응답 형식이 올바르지 않습니다")
    for grade, classes in enumerate(data):
        if (not isinstance(classes, (list, tuple)) or len(classes) > 100
                or (grade == 0 and classes)):
            raise RuntimeError("시간표 응답 형식이 올바르지 않습니다")
        for class_number, days in enumerate(classes):
            if (not isinstance(days, (list, tuple)) or len(days) > 8
                    or (class_number == 0 and days)):
                raise RuntimeError("시간표 응답 형식이 올바르지 않습니다")
            for day, lessons in enumerate(days):
                if day < 1 or day > 5:
                    continue
                if not isinstance(lessons, (list, tuple)) or len(lessons) > 30:
                    raise RuntimeError("시간표 응답 형식이 올바르지 않습니다")
                for lesson in lessons:
                    if (not isinstance(getattr(lesson, "subject", None), str)
                            or not isinstance(getattr(lesson, "teacher", None), str)
                            or not isinstance(getattr(lesson, "replaced", None), bool)
                            or not isinstance(getattr(lesson, "period", None), int)
                            or isinstance(lesson.period, bool) or lesson.period < 1):
                        raise RuntimeError("시간표 응답 형식이 올바르지 않습니다")
                    if not lesson.subject and not lesson.teacher and not lesson.replaced:
                        continue
                    records.append({"grade": grade, "class": class_number,
                        "date": (start + timedelta(days=day - 1)).isoformat(),
                        "period": lesson.period, "subject": lesson.subject,
                        "teacher": lesson.teacher, "isChanged": lesson.replaced})
    updated_at = None
    if timetable.update_date:
        try:
            updated = datetime.fromisoformat(str(timetable.update_date))
        except ValueError as exc:
            raise RuntimeError("시간표 갱신 시각이 올바르지 않습니다") from exc
        kst = timezone(timedelta(hours=9))
        updated_at = (updated.replace(tzinfo=kst) if updated.tzinfo is None
                      else updated.astimezone(kst)).isoformat()
    return {"schoolId": school_id, "weekStart": week, "records": records,
        "sourceUpdatedAt": updated_at,
        "fetchedAt": datetime.now(timezone.utc).isoformat(), "stale": False}
