"""Create an all-day calendar feed from cached timetable records."""

import hashlib
from datetime import date, datetime, timedelta, timezone


def _escape(value):
    return str(value).replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def _fold(line):
    parts = []
    current = ""
    size = 0
    for char in line:
        width = len(char.encode("utf-8"))
        if size + width > 75:
            parts.append(current)
            current = " "
            size = 1
        current += char
        size += width
    parts.append(current)
    return parts


def _stamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        parsed = datetime.now(timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def render_timetable_ics(school, grade, classroom, timetables):
    name = school.split(":", 1)[1]
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Opencigan//Timetable//KO",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:" + _escape(f"{name} {grade}학년 {classroom}반"),
        "REFRESH-INTERVAL;VALUE=DURATION:PT30M",
    ]
    for timetable in timetables:
        timestamp = _stamp(timetable.get("sourceUpdatedAt") or timetable.get("fetchedAt"))
        for record in timetable["records"]:
            if int(record["grade"]) != grade or int(record["class"]) != classroom:
                continue
            day = date.fromisoformat(record["date"])
            period = int(record["period"])
            identity = f"{school}|{grade}|{classroom}|{day.isoformat()}|{period}"
            uid = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32] + "@opencigan"
            subject = record.get("subject") or "수업"
            details = [f"{period}교시", f"교사: {record['teacher']}"] if record.get("teacher") else [f"{period}교시"]
            if record.get("isChanged"):
                details.append("변경된 수업")
            lines.extend([
                "BEGIN:VEVENT", "UID:" + uid, "DTSTAMP:" + timestamp,
                "DTSTART;VALUE=DATE:" + day.strftime("%Y%m%d"),
                "DTEND;VALUE=DATE:" + (day + timedelta(days=1)).strftime("%Y%m%d"),
                "SUMMARY:" + _escape(f"{period}교시 {subject}"),
                "DESCRIPTION:" + _escape("\n".join(details)), "END:VEVENT",
            ])
    lines.append("END:VCALENDAR")
    return ("\r\n".join(part for line in lines for part in _fold(line)) + "\r\n").encode("utf-8")
