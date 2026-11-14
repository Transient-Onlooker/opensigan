import hmac
import json
import logging
import os
import re
import sqlite3
import socketserver
import threading
import time
import wsgiref.simple_server
from collections import OrderedDict, deque
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from backend.cache import Cache
from backend.analytics import ApiRecorder
from backend.ical import render_timetable_ics
from backend.shutter import Shutter
from backend.neis import NEISClient, School
from backend.timetable import fetch_timetable, search_schools, validate_timetable_week

cache = Cache()
shutter = Shutter.from_environment()
logger = logging.getLogger("opensigan")
_rate_lock = threading.Lock()
_rate_clients = OrderedDict()
_analytics_lock = threading.Lock()
_analytics_instance = None


def _analytics_store():
    global _analytics_instance
    path = os.environ.get("OPENCIGAN_ANALYTICS_DB", "").strip()
    secret = os.environ.get("OPENCIGAN_ANALYTICS_SECRET", "")
    if not path or len(secret) < 32:
        return None
    with _analytics_lock:
        if _analytics_instance is None or _analytics_instance.path != path or _analytics_instance.secret != secret.encode("utf-8"):
            from backend.analytics import AnalyticsStore
            _analytics_instance = AnalyticsStore(path, secret)
        return _analytics_instance


def _rate_allowed(client):
    now = time.monotonic()
    with _rate_lock:
        while _rate_clients and next(iter(_rate_clients.values()))[-1] <= now - 60:
            _rate_clients.popitem(last=False)
        if client not in _rate_clients and len(_rate_clients) >= 4096:
            _rate_clients.popitem(last=False)
        requests = _rate_clients.setdefault(client, deque())
        while requests and requests[0] <= now - 60:
            requests.popleft()
        _rate_clients.move_to_end(client)
        if len(requests) >= 60:
            return max(1, int(61 - (now - requests[0])))
        requests.append(now)
        return 0


def _history_store():
    path = os.environ.get("OPENCIGAN_HISTORY_DB", "").strip()
    if not path:
        return None
    from backend.history import HistoryStore
    return HistoryStore(path)


def _query_param(params, key, limit):
    values = params.get(key, [])
    if len(values) != 1 or not values[0].strip() or len(values[0]) > limit:
        raise ValueError(f"{key} 값이 올바르지 않습니다")
    return values[0].strip()


def _timetable_filters(query, require_class=False):
    grade_filter = None
    class_filter = None
    teacher_filter = None
    if require_class or "grade" in query:
        raw_grade = _query_param(query, "grade", 1)
        if not re.fullmatch(r"[1-6]", raw_grade):
            raise ValueError("grade는 1부터 6까지의 정수여야 합니다")
        grade_filter = int(raw_grade)
    if require_class or "class" in query:
        raw_class = _query_param(query, "class", 2)
        if not re.fullmatch(r"[1-9][0-9]?", raw_class):
            raise ValueError("class는 1부터 99까지의 정수여야 합니다")
        class_filter = int(raw_class)
    if "teacher" in query:
        teacher_filter = _query_param(query, "teacher", 50).casefold()
    return grade_filter, class_filter, teacher_filter


def _cached_timetable(school, week, current_cache):
    def fetch_and_record():
        started_at = datetime.now(timezone.utc).isoformat()
        data = fetch_timetable(school, week)
        try:
            store = _history_store()
            if store is not None and not data.get("stale", False):
                store.observe(school, week, data["records"], observed_at=data["fetchedAt"], started_at=started_at)
        except Exception:
            logger.exception("history recording failed")
        return data

    return current_cache.get(("timetable", school, week), fetch_and_record, with_status=True)


def _read_request_body(stream, content_length):
    try:
        length = int(content_length or "0")
    except (TypeError, ValueError):
        return b""
    if length < 0:
        return b""
    if length > 4096:
        return b" " * 4097
    return stream.read(length) if stream is not None else b""


def _dispatch_request(method, path, query_string, cache_instance=None, client=None, request_origin=None, request_body=None, request_headers=None, shutter_instance=None):
    current_cache = cache if cache_instance is None else cache_instance
    origin = os.environ.get("ALLOWED_ORIGIN", "")

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
    }
    if origin:
        headers["Vary"] = "Origin"
    if origin and (request_origin is None or request_origin in [item.strip() for item in origin.split(",")]):
        headers["Access-Control-Allow-Origin"] = request_origin or origin.split(",")[0].strip()
        headers["Access-Control-Expose-Headers"] = "Retry-After"

    if method == "OPTIONS":
        headers["Access-Control-Allow-Methods"] = "GET, HEAD, POST, OPTIONS"
        headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        headers["Access-Control-Expose-Headers"] = "Retry-After"
        headers["Content-Length"] = "0"
        return 204, headers, b""

    if path not in ("/api/v1/status", "/api/v1/admin/analytics"):
        allowed, retry_after = (shutter if shutter_instance is None else shutter_instance).check()
        if not allowed:
            body = json.dumps({"error": "요청이 집중되어 일시적으로 중단되었습니다. 잠시 후 다시 시도해 주세요.", "code": "service_overloaded", "retry_after": retry_after}, ensure_ascii=False).encode("utf-8")
            headers["Retry-After"] = str(retry_after)
            headers["Content-Length"] = str(len(body))
            return 503, headers, body

    if path == "/api/v1/analytics/pageview":
        if method != "POST":
            body = json.dumps({"error": "지원하지 않는 메서드입니다", "code": "method_not_allowed"}, ensure_ascii=False).encode("utf-8")
            headers["Content-Length"] = str(len(body))
            return 405, headers, body
        if len(request_body or b"") > 4096:
            body = json.dumps({"error": "요청 본문이 너무 큽니다", "code": "payload_too_large"}, ensure_ascii=False).encode("utf-8")
            headers["Content-Length"] = str(len(body))
            return 413, headers, body
        try:
            store = _analytics_store()
        except (OSError, sqlite3.Error):
            store = None
        if store is None:
            body = json.dumps({"error": "분석 저장소가 설정되지 않았습니다", "code": "analytics_disabled"}, ensure_ascii=False).encode("utf-8")
            headers["Content-Length"] = str(len(body))
            return 503, headers, body
        if client:
            retry = _rate_allowed(("analytics", client))
            if retry:
                body = json.dumps({"error": "요청이 너무 많습니다", "code": "rate_limited"}, ensure_ascii=False).encode("utf-8")
                headers["Retry-After"] = str(retry)
                headers["Content-Length"] = str(len(body))
                return 429, headers, body
        try:
            payload = json.loads(request_body or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("analytics payload must be an object")
            store.record_pageview(payload.get("visitorId"), payload.get("sessionId"), payload.get("page"))
        except (ValueError, TypeError, AttributeError):
            body = json.dumps({"error": "분석 이벤트가 올바르지 않습니다", "code": "invalid_request"}, ensure_ascii=False).encode("utf-8")
            headers["Content-Length"] = str(len(body))
            return 400, headers, body
        except (OSError, sqlite3.Error):
            body = b'{"error":"Analytics temporarily unavailable","code":"analytics_unavailable"}'
            headers["Content-Length"] = str(len(body))
            return 503, headers, body
        body = b'{"accepted":true}'
        headers["Content-Length"] = str(len(body))
        return 202, headers, body

    if path == "/api/v1/admin/analytics":
        if method not in ("GET", "HEAD"):
            body = json.dumps({"error": "지원하지 않는 메서드입니다", "code": "method_not_allowed"}, ensure_ascii=False).encode("utf-8")
            headers["Content-Length"] = str(len(body))
            return 405, headers, body
        token = os.environ.get("OPENCIGAN_ANALYTICS_ADMIN_TOKEN", "")
        supplied = (request_headers or {}).get("Authorization", "")
        if not token or not hmac.compare_digest(supplied.encode("utf-8"), f"Bearer {token}".encode("utf-8")):
            headers["WWW-Authenticate"] = 'Bearer realm="OpenSigan analytics"'
            body = json.dumps({"error": "인증이 필요합니다", "code": "unauthorized"}, ensure_ascii=False).encode("utf-8")
            headers["Content-Length"] = str(len(body))
            return 401, headers, body
        try:
            store = _analytics_store()
        except (OSError, sqlite3.Error):
            store = None
        if store is None:
            body = json.dumps({"error": "분석 저장소가 설정되지 않았습니다", "code": "analytics_disabled"}, ensure_ascii=False).encode("utf-8")
            headers["Content-Length"] = str(len(body))
            return 503, headers, body
        try:
            values = parse_qs(query_string, keep_blank_values=True).get("days", ["30"])
            if len(values) != 1 or not re.fullmatch(r"(?:[1-9]|[1-8][0-9]|90)", values[0]):
                raise ValueError("조회 기간은 1~90일이어야 합니다")
            days = int(values[0])
            result = store.summary(days)
            result["droppedApiEvents"] = _api_recorder.dropped
        except (ValueError, TypeError):
            body = json.dumps({"error": "조회 기간은 1~90일이어야 합니다", "code": "invalid_request"}, ensure_ascii=False).encode("utf-8")
            headers["Content-Length"] = str(len(body))
            return 400, headers, body
        except (OSError, sqlite3.Error):
            body = b'{"error":"Analytics temporarily unavailable","code":"analytics_unavailable"}'
            headers["Content-Length"] = str(len(body))
            return 503, headers, body
        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        headers["Content-Length"] = str(len(body))
        return 200, headers, body

    if method not in ("GET", "HEAD"):
        body = json.dumps({"error": "지원하지 않는 메서드입니다", "code": "method_not_allowed"}, ensure_ascii=False).encode("utf-8")
        headers["Content-Length"] = str(len(body))
        return 405, headers, body

    if client and path != "/api/v1/status":
        retry = _rate_allowed(client)
        if retry:
            body = json.dumps({"error": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.", "code": "rate_limited"}, ensure_ascii=False).encode("utf-8")
            headers["Retry-After"] = str(retry)
            headers["Content-Length"] = str(len(body))
            return 429, headers, body
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
            grade_filter, class_filter, teacher_filter = _timetable_filters(query)
            timetable, cache_status = _cached_timetable(school, week, current_cache)
            result = {**timetable, "cacheStatus": cache_status}
            if grade_filter is not None or class_filter is not None or teacher_filter is not None:
                result["records"] = [record for record in timetable["records"]
                                     if (grade_filter is None or int(record["grade"]) == grade_filter)
                                     and (class_filter is None or int(record["class"]) == class_filter)
                                     and (teacher_filter is None or teacher_filter in (record.get("teacher") or "").casefold())]
        elif path == "/api/v1/timetable.ics":
            school = _query_param(query, "school", 100)
            if not re.fullmatch(r"[0-9]+:[^:]{1,50}", school):
                raise ValueError("학교 식별자가 올바르지 않습니다")
            grade_filter, class_filter, teacher_filter = _timetable_filters(query, require_class=True)
            weeks = _query_param(query, "weeks", 1) if "weeks" in query else "1"
            if weeks not in ("1", "2"):
                raise ValueError("weeks는 1 또는 2여야 합니다")
            now = datetime.now(timezone(timedelta(hours=9))).date()
            monday = now - timedelta(days=now.weekday())
            timetables = []
            for offset in range(int(weeks)):
                week = (monday + timedelta(days=offset * 7)).isoformat()
                timetable, _ = _cached_timetable(school, week, current_cache)
                if teacher_filter is not None:
                    timetable = {**timetable, "records": [r for r in timetable["records"]
                                 if teacher_filter in (r.get("teacher") or "").casefold()]}
                timetables.append(timetable)
            body = render_timetable_ics(school, grade_filter, class_filter, timetables)
            headers["Content-Type"] = "text/calendar; charset=utf-8"
            headers["Content-Disposition"] = 'inline; filename="opencigan.ics"'
            headers["Content-Length"] = str(len(body))
            return 200, headers, body
        elif path == "/api/v1/timetable/history":
            school = _query_param(query, "school", 100)
            if not re.fullmatch(r"[0-9]+:[^:]{1,50}", school):
                raise ValueError("학교 식별자가 올바르지 않습니다")
            week = _query_param(query, "week", 10)
            parsed_week = date.fromisoformat(week)
            if parsed_week.isoformat() != week or parsed_week.weekday() != 0:
                raise ValueError("주 시작일이 올바르지 않습니다")
            cursor = _query_param(query, "cursor", 100) if "cursor" in query else None
            store = _history_store()
            if store is None:
                body = json.dumps({"error": "변경 이력 저장이 활성화되지 않았습니다", "code": "history_disabled"}, ensure_ascii=False).encode("utf-8")
                headers["Content-Length"] = str(len(body))
                return 503, headers, body
            result = store.list(school, week, cursor=cursor)
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
            body = json.dumps({"error": "요청한 경로가 없습니다", "code": "not_found"}, ensure_ascii=False).encode("utf-8")
            headers["Content-Length"] = str(len(body))
            return 404, headers, body

        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        headers["Content-Length"] = str(len(body))
        return 200, headers, body
    except ValueError as exc:
        body = json.dumps({"error": str(exc), "code": "invalid_request"}, ensure_ascii=False).encode("utf-8")
        headers["Content-Length"] = str(len(body))
        return 400, headers, body
    except Exception:
        logger.exception("upstream request failed")
        body = json.dumps(
            {"error": "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.", "code": "upstream_unavailable"},
            ensure_ascii=False,
        ).encode("utf-8")
        headers["Content-Length"] = str(len(body))
        return 503, headers, body


_api_recorder = ApiRecorder(_analytics_store)


def dispatch_request(method, path, query_string, cache_instance=None, client=None, request_origin=None, request_body=None, request_headers=None, shutter_instance=None):
    started = time.perf_counter()
    response = _dispatch_request(method, path, query_string, cache_instance, client, request_origin, request_body, request_headers, shutter_instance)
    if method in ("GET", "HEAD") and path in ("/api/v1/schools", "/api/v1/neis/schools", "/api/v1/timetable", "/api/v1/timetable.ics", "/api/v1/timetable/history", "/api/v1/meals") and os.environ.get("OPENCIGAN_ANALYTICS_DB"):
        _api_recorder.submit(path, method, response[0], (time.perf_counter() - started) * 1000)
    return response


class Handler(BaseHTTPRequestHandler):
    def _unsupported(self):
        parts = urlsplit(self.path)
        request_body = _read_request_body(self.rfile, self.headers.get("Content-Length")) if self.command == "POST" and parts.path == "/api/v1/analytics/pageview" else None
        status_code, headers, body = dispatch_request(self.command, parts.path, parts.query, cache, self.client_address[0], self.headers.get("Origin"), request_body, {"Authorization": self.headers.get("Authorization", "")})
        self.send_response(status_code)
        for key, val in headers.items():
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_PUT = do_PATCH = do_DELETE = _unsupported

    def do_OPTIONS(self):
        parts = urlsplit(self.path)
        status_code, headers, body = dispatch_request("OPTIONS", parts.path, parts.query, cache, request_origin=self.headers.get("Origin"))
        self.send_response(status_code)
        for key, val in headers.items():
            self.send_header(key, val)
        self.end_headers()

    def do_HEAD(self):
        parts = urlsplit(self.path)
        status_code, headers, body = dispatch_request("HEAD", parts.path, parts.query, cache, self.client_address[0], self.headers.get("Origin"), request_headers={"Authorization": self.headers.get("Authorization", "")})
        self.send_response(status_code)
        for key, val in headers.items():
            self.send_header(key, val)
        self.end_headers()

    def do_GET(self):
        parts = urlsplit(self.path)
        status_code, headers, body = dispatch_request("GET", parts.path, parts.query, cache, self.client_address[0], self.headers.get("Origin"), request_headers={"Authorization": self.headers.get("Authorization", "")})
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
    202: "202 Accepted",
    204: "204 No Content",
    400: "400 Bad Request",
    401: "401 Unauthorized",
    404: "404 Not Found",
    405: "405 Method Not Allowed",
    429: "429 Too Many Requests",
    413: "413 Payload Too Large",
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
            client=environ.get("REMOTE_ADDR"),
            request_origin=environ.get("HTTP_ORIGIN"),
            request_body=_read_request_body(environ.get("wsgi.input"), environ.get("CONTENT_LENGTH")) if method == "POST" and path == "/api/v1/analytics/pageview" else None,
            request_headers={"Authorization": environ.get("HTTP_AUTHORIZATION", "")},
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
