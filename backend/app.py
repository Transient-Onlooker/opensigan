import json
import logging
import os
import re
import socketserver
import wsgiref.simple_server
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from backend.cache import Cache
from backend.neis import NEISClient, School
from backend.timetable import fetch_timetable, search_schools, validate_timetable_week

cache = Cache()
logger = logging.getLogger("opensigan")


def _query_param(params, key, limit):
    values = params.get(key, [])
    if len(values) != 1 or not values[0].strip() or len(values[0]) > limit:
        raise ValueError(f"{key} 값이 올바르지 않습니다")
    return values[0].strip()


def dispatch_request(method, path, query_string, cache_instance=None):
    current_cache = cache if cache_instance is None else cache_instance
    origin = os.environ.get("ALLOWED_ORIGIN", "")

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
    }
    if origin:
        headers["Access-Control-Allow-Origin"] = origin

    if method == "OPTIONS":
        headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
        headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        headers["Content-Length"] = "0"
        return 204, headers, b""

    if method not in ("GET", "HEAD"):
        body = json.dumps({"error": "지원하지 않는 메서드입니다"}, ensure_ascii=False).encode("utf-8")
        headers["Content-Length"] = str(len(body))
        return 405, headers, body

    query = parse_qs(query_string)
    try:
        if path == "/api/v1/status":
            result = {"status": "ok", "scope": "process liveness"}
        elif path == "/api/v1/schools":
            name = _query_param(query, "q", 50)

            def fetch_school_search():
                try:
                    return {"schools": search_schools(name), "stale": False}
                except ValueError as exc:
                    raise RuntimeError("school search failed") from exc

            result = current_cache.get(("school_search", name), fetch_school_search)
        elif path == "/api/v1/timetable":
            school = _query_param(query, "school", 100)
            if not re.fullmatch(r"[0-9]+:[^:]{1,50}", school):
                raise ValueError("학교 식별자가 올바르지 않습니다")
            week = _query_param(query, "week", 10)
            validate_timetable_week(week)
            result = current_cache.get(("timetable", school, week), lambda: fetch_timetable(school, week))
        elif path == "/api/v1/neis/schools":
            name = _query_param(query, "q", 50)
            if not os.environ.get("NEIS_API_KEY", "").strip():
                raise RuntimeError("NEIS API key is not configured")

            def fetch_schools():
                try:
                    schools = NEISClient.from_environment().search_schools(name)
                except ValueError as exc:
                    raise RuntimeError("NEIS school search failed") from exc
                return {
                    "schools": [
                        {
                            "id": f"{s.office_code}:{s.school_code}",
                            "name": s.name,
                            "region": s.kind,
                            "address": s.address,
                        }
                        for s in schools
                    ],
                    "stale": False,
                }

            result = current_cache.get(("neis_school_search", name), fetch_schools)
        elif path == "/api/v1/meals":
            school_id = _query_param(query, "school", 20)
            if not re.fullmatch(r"[A-Z]\d{2}:\d{7}", school_id):
                raise ValueError("급식 학교 식별자가 올바르지 않습니다")
            start = date.fromisoformat(_query_param(query, "from", 10))
            end = date.fromisoformat(_query_param(query, "to", 10))
            if end < start or (end - start).days > 6:
                raise ValueError("급식은 최대 7일 동안 조회할 수 있습니다")
            office, code = school_id.split(":")
            school = School(office, code, "")
            if not os.environ.get("NEIS_API_KEY", "").strip():
                raise RuntimeError("NEIS API key is not configured")

            def fetch_meals():
                meals = NEISClient.from_environment().get_meals(school, start, end)
                return {
                    "meals": [
                        {
                            "date": m.date,
                            "type": m.meal_type,
                            "dishes": re.split(r"<br\s*/?>", m.menu, flags=re.I),
                        }
                        for m in meals
                    ],
                    "stale": False,
                }

            result = current_cache.get(("meals", school_id, start, end), fetch_meals)
        else:
            body = json.dumps({"error": "요청한 경로가 없습니다"}, ensure_ascii=False).encode("utf-8")
            headers["Content-Length"] = str(len(body))
            return 404, headers, body

        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        headers["Content-Length"] = str(len(body))
        return 200, headers, body
    except ValueError as exc:
        body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
        headers["Content-Length"] = str(len(body))
        return 400, headers, body
    except Exception:
        logger.exception("upstream request failed")
        body = json.dumps(
            {"error": "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."},
            ensure_ascii=False,
        ).encode("utf-8")
        headers["Content-Length"] = str(len(body))
        return 503, headers, body


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        parts = urlsplit(self.path)
        status_code, headers, body = dispatch_request("OPTIONS", parts.path, parts.query, cache)
        self.send_response(status_code)
        for key, val in headers.items():
            self.send_header(key, val)
        self.end_headers()

    def do_HEAD(self):
        parts = urlsplit(self.path)
        status_code, headers, body = dispatch_request("HEAD", parts.path, parts.query, cache)
        self.send_response(status_code)
        for key, val in headers.items():
            self.send_header(key, val)
        self.end_headers()

    def do_GET(self):
        parts = urlsplit(self.path)
        status_code, headers, body = dispatch_request("GET", parts.path, parts.query, cache)
        self.send_response(status_code)
        for key, val in headers.items():
            self.send_header(key, val)
        self.end_headers()
        if body:
            self.wfile.write(body)

    @staticmethod
    def query(params, key, limit):
        return _query_param(params, key, limit)

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


_STATUS_PHRASES = {
    200: "200 OK",
    204: "204 No Content",
    400: "400 Bad Request",
    404: "404 Not Found",
    405: "405 Method Not Allowed",
    500: "500 Internal Server Error",
    503: "503 Service Unavailable",
}


def make_app(cache_instance=None):
    """Create a PEP 3333 compliant WSGI application."""

    def wsgi_application(environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "") or "/"
        query_string = environ.get("QUERY_STRING", "")

        status_code, headers, body = dispatch_request(
            method=method,
            path=path,
            query_string=query_string,
            cache_instance=cache_instance,
        )

        status_line = _STATUS_PHRASES.get(status_code, f"{status_code} Unknown")
        start_response(status_line, list(headers.items()))
        if method == "HEAD":
            return [b""]
        return [body]

    return wsgi_application


app = make_app()
application = app


class ThreadingWSGIServer(socketserver.ThreadingMixIn, wsgiref.simple_server.WSGIServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(host=None, port=None, wsgi_app=None):
    host = host or os.environ.get("HOST", "127.0.0.1")
    port = int(port or os.environ.get("PORT", "8000"))
    target_app = wsgi_app or app

    try:
        import waitress

        threads = int(os.environ.get("THREADS", "8"))
        logger.info("Starting Waitress WSGI server on %s:%s (threads=%d)", host, port, threads)
        waitress.serve(target_app, host=host, port=port, threads=threads)
    except ImportError:
        logger.info("Waitress not installed. Serving with ThreadingWSGIServer on %s:%s", host, port)
        server = wsgiref.simple_server.make_server(
            host, port, target_app, server_class=ThreadingWSGIServer
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve()
