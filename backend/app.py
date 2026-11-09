import json
import logging
import os
import re
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from backend.cache import Cache
from backend.neis import NEISClient, School
from backend.timetable import fetch_timetable, search_schools

cache = Cache()
logger = logging.getLogger("opensigan")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        origin = os.environ.get("ALLOWED_ORIGIN", "")
        parts = urlsplit(self.path)
        query = parse_qs(parts.query)
        try:
            if parts.path == "/api/v1/status":
                result = {"status": "ok"}
            elif parts.path == "/api/v1/schools":
                name = self.query(query, "q", 50)
                result = {"schools": search_schools(name)}
            elif parts.path == "/api/v1/timetable":
                school = self.query(query, "school", 100)
                if not re.fullmatch(r"[0-9]+:[^:]{1,50}", school):
                    raise ValueError("학교 식별자가 올바르지 않습니다")
                week = self.query(query, "week", 10)
                result = cache.get(("timetable", school, week), lambda: fetch_timetable(school, week))
            elif parts.path == "/api/v1/neis/schools":
                name = self.query(query, "q", 50)
                if not os.environ.get("NEIS_API_KEY", "").strip():
                    raise RuntimeError("NEIS API key is not configured")
                schools = NEISClient.from_environment().search_schools(name)
                result = {"schools": [{"id": f"{s.office_code}:{s.school_code}",
                    "name": s.name, "region": s.kind, "address": s.address} for s in schools]}
            elif parts.path == "/api/v1/meals":
                school_id = self.query(query, "school", 20)
                if not re.fullmatch(r"[A-Z]\d{2}:\d{7}", school_id):
                    raise ValueError("급식 학교 식별자가 올바르지 않습니다")
                start = date.fromisoformat(self.query(query, "from", 10))
                end = date.fromisoformat(self.query(query, "to", 10))
                if end < start or (end - start).days > 6:
                    raise ValueError("급식은 최대 7일 동안 조회할 수 있습니다")
                office, code = school_id.split(":")
                school = School(office, code, "")
                if not os.environ.get("NEIS_API_KEY", "").strip():
                    raise RuntimeError("NEIS API key is not configured")
                def fetch_meals():
                    meals = NEISClient.from_environment().get_meals(school, start, end)
                    return {"meals": [{"date": m.date, "type": m.meal_type,
                        "dishes": re.split(r"<br\s*/?>", m.menu, flags=re.I)} for m in meals], "stale": False}

                result = cache.get(("meals", school_id, start, end), fetch_meals)
            else:
                self.respond(404, {"error": "요청한 경로가 없습니다"}, origin)
                return
        except ValueError as exc:
            self.respond(400, {"error": str(exc)}, origin)
            return
        except Exception:
            logger.exception("upstream request failed")
            self.respond(503, {"error": "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."}, origin)
            return
        self.respond(200, result, origin)

    @staticmethod
    def query(params, key, limit):
        values = params.get(key, [])
        if len(values) != 1 or not values[0].strip() or len(values[0]) > limit:
            raise ValueError(f"{key} 값이 올바르지 않습니다")
        return values[0].strip()

    def respond(self, status, result, origin):
        data = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ThreadingHTTPServer((os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8000"))), Handler).serve_forever()
