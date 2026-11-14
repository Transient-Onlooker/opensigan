import json
import unittest
import io
import sqlite3
import threading
from contextlib import closing
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from backend.analytics import AnalyticsStore, ApiRecorder
from backend.app import Handler, dispatch_request, _read_request_body, _rate_clients


class AnalyticsTests(unittest.TestCase):
    def store(self):
        store = AnalyticsStore(":memory:", "x" * 40)
        self.addCleanup(store.close)
        return store

    def test_aggregates_anonymous_visitors_sessions_and_api_metrics(self):
        store = self.store()
        store.record_pageview("11111111-1111-4111-8111-111111111111", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "/timetable")
        store.record_pageview("11111111-1111-4111-8111-111111111111", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "/meals")
        store.record_pageview("22222222-2222-4222-8222-222222222222", "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "/")
        store.record_api("/api/v1/timetable", "GET", 200, 12.5)
        store.record_api("/api/v1/meals", "GET", 503, 30)
        result = store.summary(30)
        self.assertEqual((result["visitors"], result["sessions"], result["pageViews"]), (2, 3, 3))
        self.assertEqual((result["apiRequests"], result["apiErrors"]), (2, 1))
        self.assertEqual(result["apiErrorRate"], 0.5)
        self.assertEqual(len(result["routes"]), 2)

    def test_pageview_endpoint_and_admin_authentication(self):
        store = self.store()
        payload = json.dumps({
            "visitorId": "11111111-1111-4111-8111-111111111111",
            "sessionId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "page": "/",
        }).encode()
        with patch("backend.app._analytics_store", return_value=store), patch.dict(
            "os.environ", {"OPENCIGAN_ANALYTICS_ADMIN_TOKEN": "admin-secret"}
        ):
            status, _, body = dispatch_request("POST", "/api/v1/analytics/pageview", "", request_body=payload)
            self.assertEqual(status, 202)
            self.assertTrue(json.loads(body)["accepted"])
            unauthorized, _, _ = dispatch_request("GET", "/api/v1/admin/analytics", "")
            self.assertEqual(unauthorized, 401)
            authorized, _, body = dispatch_request(
                "GET", "/api/v1/admin/analytics", "days=30",
                request_headers={"Authorization": "Bearer admin-secret"},
            )
            self.assertEqual(authorized, 200)
            self.assertEqual(json.loads(body)["visitors"], 1)

    def test_invalid_pageview_and_invalid_period_are_rejected(self):
        store = self.store()
        with patch("backend.app._analytics_store", return_value=store), patch.dict(
            "os.environ", {"OPENCIGAN_ANALYTICS_ADMIN_TOKEN": "admin-secret"}
        ):
            status, _, _ = dispatch_request("POST", "/api/v1/analytics/pageview", "", request_body=b"{}")
            self.assertEqual(status, 400)
            status, _, _ = dispatch_request(
                "GET", "/api/v1/admin/analytics", "days=365",
                request_headers={"Authorization": "Bearer admin-secret"},
            )
            self.assertEqual(status, 400)

    def test_retention_removes_old_rows_and_never_stores_raw_ids(self):
        store = self.store()
        visitor = "11111111-1111-4111-8111-111111111111"
        session = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        with patch.object(store, "_now", return_value=("2026-08-01", "2026-08-01T00:00:00+09:00")):
            store.record_pageview(visitor, session, "/")
            store.record_api("/api/v1/timetable", "GET", 200, 1)
        with patch.object(store, "_now", return_value=("2026-11-14", "2026-11-14T00:00:00+09:00")):
            store.record_pageview(visitor, session, "/meals")
            self.assertEqual(store.summary(90)["pageViews"], 1)
        with closing(store._connect()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM api_requests").fetchone()[0], 0)
            row = db.execute("SELECT visitor_hash, session_hash FROM page_views").fetchone()
            self.assertNotIn(visitor, tuple(row))
            self.assertNotIn(session, tuple(row))

    def test_writer_queue_is_bounded_and_does_not_wait_for_disk(self):
        entered, release = threading.Event(), threading.Event()

        class SlowStore:
            def record_api(self, *args):
                entered.set()
                release.wait(2)

        recorder = ApiRecorder(lambda: SlowStore(), capacity=1)
        try:
            recorder.submit("/api/v1/timetable", "GET", 200, 1)
            self.assertTrue(entered.wait(1))
            recorder.submit("/api/v1/timetable", "GET", 200, 1)
            recorder.submit("/api/v1/timetable", "GET", 200, 1)
            self.assertEqual(recorder.dropped, 1)
        finally:
            release.set()
            recorder.queue.join()

    def test_body_limit_rejects_without_reading_and_storage_errors_are_isolated(self):
        stream = io.BytesIO(b"abc")
        self.assertGreater(len(_read_request_body(stream, "1000000000")), 4096)
        self.assertEqual(stream.tell(), 0)
        with patch("backend.app._analytics_store", side_effect=sqlite3.OperationalError("locked")):
            self.assertEqual(dispatch_request("POST", "/api/v1/analytics/pageview", "", request_body=b"{}")[0], 503)
            self.assertEqual(dispatch_request("GET", "/api/v1/status", "")[0], 200)

    def test_native_http_handler_forwards_admin_auth_for_get_and_head(self):
        store = self.store()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with patch("backend.app._analytics_store", return_value=store), patch.dict(
                "os.environ", {"OPENCIGAN_ANALYTICS_ADMIN_TOKEN": "admin-secret"}
            ):
                for method in ("GET", "HEAD"):
                    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    try:
                        conn.request(method, "/api/v1/admin/analytics", headers={"Authorization": "Bearer admin-secret"})
                        response = conn.getresponse()
                        self.assertEqual(response.status, 200)
                        body = response.read()
                        if method == "HEAD":
                            self.assertEqual(body, b"")
                    finally:
                        conn.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_analytics_rate_limit_does_not_exhaust_data_limit(self):
        _rate_clients.clear()
        with patch("backend.app._analytics_store", return_value=self.store()):
            for _ in range(60):
                dispatch_request("POST", "/api/v1/analytics/pageview", "", client="analytics-test", request_body=b"{}")
            self.assertEqual(dispatch_request("POST", "/api/v1/analytics/pageview", "", client="analytics-test", request_body=b"{}")[0], 429)
            self.assertEqual(dispatch_request("GET", "/api/v1/schools", "", client="analytics-test")[0], 400)
        _rate_clients.clear()


if __name__ == "__main__":
    unittest.main()
