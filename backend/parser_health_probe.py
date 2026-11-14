"""One-shot upstream parser health check; intentionally no retries or timetable fetches."""

import re

from backend.timetable import search_schools


def check_parser():
    """Check that one live school search returns valid normalized school records."""
    schools = search_schools("대전")
    if not isinstance(schools, list) or not schools:
        raise RuntimeError("School search returned no valid results")
    for school in schools:
        if (not isinstance(school, dict)
                or not isinstance(school.get("id"), str)
                or not re.fullmatch(r"[0-9]+:[^:]{1,50}", school["id"])
                or not isinstance(school.get("name"), str) or not school["name"]
                or not isinstance(school.get("region"), str)):
            raise RuntimeError("School search response shape changed")
    return len(schools)


if __name__ == "__main__":
    count = check_parser()
    print(f"Parser health passed: {count} schools matched; one school search, no timetable fetch.")
