import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_d1_cache import SQLiteD1, MockD1

class Response:
    def __init__(self, body, status=200, headers=None):
        self.body, self.status, self.headers = body, status, headers

workers = types.ModuleType("workers")
workers.Response = Response
workers.WorkerEntrypoint = object
sys.modules["workers"] = workers
spec = importlib.util.spec_from_file_location("worker", Path(__file__).with_name("worker.py"))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

class ContractTest(unittest.TestCase):
    def setUp(self):
        temp_dir = Path.home() / "AppData" / "Local" / "Temp" if os.name == "nt" else None
        self.temp = tempfile.TemporaryDirectory(dir=temp_dir)
        self.addCleanup(self.temp.cleanup)
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        self.db = SQLiteD1(schema, str(Path(self.temp.name) / "cache.sqlite"))

    def request(self, path, method="GET", key=None, db=True):
        request = types.SimpleNamespace(url="http://localhost" + path, method=method)
        handler = worker.Default()
        bindings = {"NEIS_API_KEY": key} if key is not None else {}
        if db:
            bindings["DB"] = self.db
        handler.env = types.SimpleNamespace(**bindings)
        response = asyncio.run(handler.fetch(request))
        return response.status, json.loads(response.body)

    def test_status_and_bad_inputs(self):
        self.assertEqual(self.request("/status"), (200, {"status": "ok", "scope": "process liveness"}))
        for path in ("/api/v1/schools", "/api/v1/schools?q=&q=a",
                     "/timetable?school=0:school&week=2026-11-09",
                     "/timetable?school=1:school&week=bad"):
            self.assertEqual(self.request(path)[0], 400)
        self.assertEqual(self.request("/other")[0], 404)
        self.assertEqual(self.request("/status", "POST")[0], 405)

    def test_search_and_timetable_contracts(self):
        today = datetime.now(timezone(timedelta(hours=9))).date()
        week = (today - timedelta(days=today.weekday())).isoformat()
        with patch.object(worker, "search_schools", return_value=[{"id": "1:school", "name": "school", "region": "r"}]) as search:
            status, body = self.request("/api/v1/schools?q=school")
            self.assertEqual((status, body["stale"], body["schools"][0]["id"]), (200, False, "1:school"))
            search.assert_called_once_with("school")
        expected = {"schoolId": "1:school", "weekStart": week, "records": [], "sourceUpdatedAt": None, "fetchedAt": "x", "stale": False}
        with patch.object(worker, "fetch_timetable", return_value=expected) as fetch:
            self.assertEqual(self.request("/api/v1/timetable?school=1%3Aschool&week=" + week), (200, expected))
            fetch.assert_called_once_with("1:school", week)

    def test_upstream_errors_do_not_leak(self):
        for error in (ValueError("private data"), RuntimeError("private data")):
            with patch.object(worker, "search_schools", side_effect=error):
                self.assertEqual(self.request("/schools?q=x"), (503, {"error": "upstream unavailable"}))
        today = datetime.now(timezone(timedelta(hours=9))).date()
        week = (today - timedelta(days=today.weekday())).isoformat()
        with patch.object(worker, "fetch_timetable", side_effect=RuntimeError("private data")):
            self.assertEqual(self.request("/timetable?school=1%3Aschool&week=" + week), (503, {"error": "upstream unavailable"}))

    def test_neis_contracts(self):
        with patch.object(worker, "NEISClient") as factory:
            client = factory.return_value
            client.search_schools.return_value = [worker.School("B10", "1234567", "school", "high", "address")]
            client.get_meals.return_value = [types.SimpleNamespace(date="2026-11-10", meal_type="lunch", menu="rice(1)<BR />soup(2)")]
            self.assertEqual(self.request("/api/v1/neis/schools?q=school", key="mock-key"),
                (200, {"schools": [{"id": "B10:1234567", "name": "school", "region": "high", "address": "address"}], "stale": False}))
            self.assertEqual(self.request("/api/v1/meals?school=B10%3A1234567&from=2026-11-09&to=2026-11-15", key="mock-key"),
                (200, {"meals": [{"date": "2026-11-10", "type": "lunch", "dishes": ["rice(1)", "soup(2)"]}], "stale": False}))
            factory.assert_called_with("mock-key", transport=worker.neis_transport)
            client.get_meals.assert_called_once_with(worker.School("B10", "1234567", ""), date(2026, 11, 9), date(2026, 11, 15))

    def test_neis_validation_and_failures(self):
        for path in ("/api/v1/neis/schools?q=", "/api/v1/neis/schools?q=a&q=b",
                     "/api/v1/meals?school=bad&from=2026-11-09&to=2026-11-15",
                     "/api/v1/meals?school=B10:1234567&from=2026-02-30&to=2026-03-01",
                     "/api/v1/meals?school=B10:1234567&from=2026-11-10&to=2026-11-09",
                     "/api/v1/meals?school=B10:1234567&from=2026-11-09&to=2026-11-16"):
            self.assertEqual(self.request(path)[0], 400)
        paths = ("/api/v1/neis/schools?q=school", "/api/v1/meals?school=B10:1234567&from=2026-11-09&to=2026-11-15")
        for path in paths:
            for key in (None, "", " "):
                self.assertEqual(self.request(path, key=key), (503, {"error": "upstream unavailable"}))
            for error in (ValueError("secret data"), RuntimeError("secret data")):
                with patch.object(worker, "NEISClient") as factory:
                    factory.return_value.search_schools.side_effect = error
                    factory.return_value.get_meals.side_effect = error
                    self.assertEqual(self.request(path, key="mock-key"), (503, {"error": "upstream unavailable"}))
        self.assertEqual(self.request("/status")[0], 200)

    def test_cache_hits_ttl_stale_backoff_and_failure(self):
        with patch.object(worker.time, "time", return_value=1000) as clock, \
             patch.object(worker, "search_schools", return_value=[{"name": "x"}]) as search:
            self.assertEqual(self.request("/schools?q=x")[1]["stale"], False)
            self.assertEqual(self.request("/api/v1/schools?q=x")[1]["stale"], False)
            search.assert_called_once()
            clock.return_value = 2800
            search.side_effect = RuntimeError("private")
            self.assertEqual(self.request("/schools?q=x")[1]["stale"], True)
            self.assertEqual(self.request("/schools?q=x")[1]["stale"], True)
            self.assertEqual(search.call_count, 2)
            clock.return_value = 2805
            search.side_effect = None
            self.assertFalse(self.request("/schools?q=x")[1]["stale"])
            self.assertEqual(search.call_count, 3)

    def test_no_db_or_broken_db_never_calls_provider(self):
        with patch.object(worker, "search_schools") as search:
            self.assertEqual(self.request("/schools?q=x", db=False)[0], 503)
            self.db = object()
            self.assertEqual(self.request("/schools?q=x")[0], 503)
            search.assert_not_called()

    def test_mock_d1_and_collision_safe_keys(self):
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        self.db = MockD1(schema, str(Path(self.temp.name) / "mock.sqlite"))
        with patch.object(worker, "search_schools", return_value=[]) as search:
            self.request("/schools?q=a%3Ab")
            self.request("/schools?q=a")
            self.request("/schools?q=a%3Ab")
            self.assertEqual(search.call_count, 2)
        self.assertTrue(any("RETURNING" in call[0] for call in self.db.calls))
        handler = worker.Default()
        handler.env = types.SimpleNamespace(DB=self.db)
        self.assertEqual(asyncio.run(handler.cached(["a:b", "c"], lambda: {"n": 1})), {"n": 1})
        self.assertEqual(asyncio.run(handler.cached(["a", "b:c"], lambda: {"n": 2})), {"n": 2})
        tokens = [params[1] for sql, params, _ in self.db.calls if "INSERT INTO d1_cache" in sql]
        self.assertEqual(len(tokens), len(set(tokens)))

    def test_corrupt_cache_never_leaks_or_calls_provider(self):
        with patch.object(worker, "search_schools", return_value=[]):
            self.assertEqual(self.request("/schools?q=private")[0], 200)
        with closing(self.db.connect()) as conn:
            conn.execute("UPDATE d1_cache SET payload = ?", ("invalid private data",))
        with patch.object(worker, "search_schools") as search:
            self.assertEqual(self.request("/schools?q=private"), (503, {"error": "upstream unavailable"}))
            search.assert_not_called()

    def test_neis_requests_transport_timeout_redirect_and_errors(self):
        with patch.object(worker.requests, "get") as get:
            get.return_value.status_code = 200
            get.return_value.content = b"response"
            self.assertEqual(worker.neis_transport("https://example.test", 8), b"response")
            get.assert_called_once_with("https://example.test", timeout=8, allow_redirects=False)
            for status in (302, 400, 500):
                get.return_value.status_code = status
                with self.assertRaises(worker.NEISNetworkError):
                    worker.neis_transport("https://example.test", 8)
            get.side_effect = worker.requests.exceptions.Timeout("secret URL")
            with self.assertRaises(worker.NEISNetworkError) as raised:
                worker.neis_transport("https://example.test", 8)
            self.assertNotIn("secret", str(raised.exception))
            self.assertTrue(raised.exception.__suppress_context__)

    def test_concurrent_cold_requests_have_one_upstream_call(self):
        started, release = threading.Event(), threading.Event()
        responses = []
        def slow(_):
            started.set()
            if not release.wait(5):
                raise RuntimeError("timeout")
            return []
        with patch.object(worker, "search_schools", side_effect=slow) as search:
            thread = threading.Thread(target=lambda: responses.append(self.request("/schools?q=race")))
            thread.start()
            try:
                self.assertTrue(started.wait(5))
                self.assertEqual(self.request("/schools?q=race")[0], 503)
            finally:
                release.set()
                thread.join(10)
            self.assertFalse(thread.is_alive())
            self.assertEqual(responses[0][0], 200)
            search.assert_called_once()

    def test_week_boundary_discards_upstream_result(self):
        with patch.object(worker, "validate_timetable_week", side_effect=[1, 0]), \
             patch.object(worker, "fetch_timetable", return_value={"stale": False}):
            self.assertEqual(self.request("/timetable?school=1%3Aschool&week=2026-11-09")[0], 503)
        with closing(self.db.connect()) as conn:
            self.assertIsNone(conn.execute("SELECT payload FROM d1_cache").fetchone()[0])

if __name__ == "__main__":
    unittest.main()
