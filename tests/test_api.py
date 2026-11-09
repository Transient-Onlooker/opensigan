import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from backend.app import Handler
from backend.cache import Cache
from backend.neis import Meal, School


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def get(self, path):
        with urlopen(self.base + path) as response:
            return json.load(response)

    def setUp(self):
        cache_patch = patch("backend.app.cache", Cache())
        cache_patch.start()
        self.addCleanup(cache_patch.stop)

    def test_status_reports_process_liveness_without_checking_upstreams(self):
        with patch("backend.app.search_schools", side_effect=RuntimeError), \
                patch("backend.app.NEISClient.from_environment", side_effect=RuntimeError):
            self.assertEqual(self.get("/api/v1/status"),
                             {"status": "ok", "scope": "process liveness"})

    def test_searches_single_flight_and_separate_sources_and_queries(self):
        school_result = [{"id": "2:school", "name": "school", "region": "region"}]
        neis_result = [{"id": "B10:1234567", "name": "school", "region": "high", "address": "address"}]
        started = threading.Event()
        release = threading.Event()

        def fetch(name):
            started.set()
            if not release.wait(5):
                raise RuntimeError("test timed out")
            return school_result

        with patch.dict("os.environ", {"NEIS_API_KEY": "test-key"}), \
                patch("backend.app.search_schools", side_effect=fetch) as search, \
                patch("backend.app.NEISClient.from_environment") as factory:
            def fetch_neis(name):
                started.set()
                if not release.wait(5):
                    raise RuntimeError("test timed out")
                return [School("B10", "1234567", "school", "high", "address")]

            factory.return_value.search_schools.side_effect = fetch_neis
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(self.get, "/api/v1/schools?q=school") for _ in range(8)]
                try:
                    self.assertTrue(started.wait(5))
                finally:
                    release.set()
                self.assertEqual([f.result(timeout=5) for f in futures], [{"schools": school_result, "stale": False}] * 8)
            started.clear()
            release.clear()
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(self.get, "/api/v1/neis/schools?q=school") for _ in range(8)]
                try:
                    self.assertTrue(started.wait(5))
                finally:
                    release.set()
                self.assertEqual([f.result(timeout=5) for f in futures], [{"schools": neis_result, "stale": False}] * 8)
            self.assertEqual(self.get("/api/v1/schools?q=other"), {"schools": school_result, "stale": False})
            self.assertEqual(search.call_count, 2)
            factory.return_value.search_schools.assert_called_once_with("school")

    def test_search_cache_expiry_failure_backoff_and_result_contract(self):
        now = [100.0]
        clock = SimpleNamespace(monotonic=lambda: now[0])
        cases = [
            ("/api/v1/schools?q=expiry", "backend.app.search_schools",
             [{"id": "2:expiry", "name": "expiry", "region": "region"}]),
            ("/api/v1/neis/schools?q=expiry", "backend.app.NEISClient.from_environment",
             [{"id": "B10:1234567", "name": "expiry", "region": "high", "address": "address"}]),
        ]
        for path, target, expected in cases:
            with self.subTest(path=path), patch("backend.app.cache", Cache(ttl=10, retry_delay=5)), \
                    patch("backend.cache.time", clock), patch.dict("os.environ", {"NEIS_API_KEY": "test-key"}), \
                    patch(target) as mocked:
                now[0] = 100
                fetch = mocked if "NEISClient" not in target else mocked.return_value.search_schools
                value = expected if fetch is mocked else [School("B10", "1234567", "expiry", "high", "address")]
                fetch.side_effect = [value, RuntimeError("upstream unavailable"), []]
                self.assertEqual(self.get(path), {"schools": expected, "stale": False})
                now[0] = 109
                self.assertEqual(self.get(path), {"schools": expected, "stale": False})
                now[0] = 110
                self.assertEqual(self.get(path), {"schools": expected, "stale": True})
                now[0] = 114
                self.assertEqual(self.get(path), {"schools": expected, "stale": True})
                self.assertEqual(fetch.call_count, 2)
                now[0] = 115
                self.assertEqual(self.get(path), {"schools": [], "stale": False})
                self.assertEqual(fetch.call_count, 3)

    def test_search_first_failure_backoff_returns_503(self):
        for path, target in [("/api/v1/schools?q=missing", "backend.app.search_schools"),
                             ("/api/v1/neis/schools?q=missing", "backend.app.NEISClient.from_environment")]:
            with self.subTest(path=path), patch("backend.app.cache", Cache(retry_delay=60)), \
                    patch.dict("os.environ", {"NEIS_API_KEY": "test-key"}), patch(target) as mocked:
                fetch = mocked if "NEISClient" not in target else mocked.return_value.search_schools
                fetch.side_effect = ValueError("secret details")
                for _ in range(2):
                    with self.assertRaises(HTTPError) as error:
                        self.get(path)
                    self.assertEqual(error.exception.code, 503)
                    self.assertNotIn("secret details", error.exception.read().decode())
                fetch.assert_called_once()

    def test_school_search_and_meals(self):
        with patch("backend.app.search_schools", return_value=[{"id": "2:school", "name": "school", "region": "region"}]):
            self.assertEqual(self.get("/api/v1/schools?q=school")["schools"][0]["id"], "2:school")
        with patch.dict("os.environ", {"NEIS_API_KEY": "test-key"}), patch("backend.app.NEISClient.from_environment") as factory:
            factory.return_value.search_schools.return_value = [School("B10", "1234567", "school", "high", "address")]
            factory.return_value.get_meals.return_value = [Meal("2026-11-10", "lunch", "rice(1)<br/>soup(2)")]
            self.assertEqual(self.get("/api/v1/neis/schools?q=school")["schools"][0]["id"], "B10:1234567")
            meals = self.get("/api/v1/meals?school=B10%3A1234567&from=2026-11-09&to=2026-11-15")
            self.assertEqual(meals["meals"][0]["dishes"], ["rice(1)", "soup(2)"])

    def test_meals_cache_reuses_school_and_date_range(self):
        with patch("backend.app.cache", Cache()), patch.dict("os.environ", {"NEIS_API_KEY": "test-key"}), \
                patch("backend.app.NEISClient.from_environment") as factory:
            factory.return_value.get_meals.return_value = [Meal("2026-11-10", "lunch", "rice(1)")]
            path = "/api/v1/meals?school=B10%3A1234567&from=2026-11-09&to=2026-11-15"

            self.assertEqual(self.get(path)["meals"][0]["dishes"], ["rice(1)"])
            self.assertEqual(self.get(path)["meals"][0]["dishes"], ["rice(1)"])

            factory.return_value.get_meals.assert_called_once()

    def test_timetable_rejects_cached_week_outside_korean_current_and_next_week(self):
        test_cache = Cache()
        invalid_week = "2026-11-02"
        test_cache.get(("timetable", "2:Example", invalid_week),
                       lambda: {"schoolId": "2:Example", "weekStart": invalid_week,
                                "records": [], "stale": False})
        for valid_week in ("2026-11-09", "2026-11-16"):
            test_cache.get(("timetable", "2:Example", valid_week),
                           lambda: {"schoolId": "2:Example", "weekStart": valid_week,
                                    "records": [], "stale": False})
        fixed_datetime = type("FixedDateTime", (), {
            "now": staticmethod(lambda tz=None: datetime(
                2026, 11, 9, 6, 1, tzinfo=timezone.utc).astimezone(tz))
        })
        with patch("backend.app.cache", test_cache), patch(
                "backend.timetable.datetime", fixed_datetime), patch(
                "backend.app.fetch_timetable") as fetch:
            for week in (invalid_week, "2026-11-23"):
                with self.subTest(week=week):
                    with self.assertRaises(HTTPError) as error:
                        self.get(f"/api/v1/timetable?school=2%3AExample&week={week}")
                    self.assertEqual(error.exception.code, 400)
            for week in ("2026-11-09", "2026-11-16"):
                with self.subTest(week=week):
                    self.assertEqual(self.get(
                        f"/api/v1/timetable?school=2%3AExample&week={week}")
                        ["weekStart"], week)
            fetch.assert_not_called()

    def test_timetable_stale_cache_and_backoff_skip_external_fetch(self):
        with patch("backend.app.cache", Cache(ttl=0, retry_delay=60)), patch(
                "backend.timetable.datetime", type("FixedDateTime", (), {
                    "now": staticmethod(lambda tz=None: datetime(
                        2026, 11, 10, tzinfo=tz))
                })), patch("backend.app.fetch_timetable") as fetch:
            fetch.side_effect = [
                {"schoolId": "2:Example", "weekStart": "2026-11-09",
                 "records": ["old"], "stale": False},
                RuntimeError("upstream unavailable"),
            ]
            path = "/api/v1/timetable?school=2%3AExample&week=2026-11-09"
            self.assertFalse(self.get(path)["stale"])
            self.assertTrue(self.get(path)["stale"])
            stale_backoff = self.get(path)
            self.assertTrue(stale_backoff["stale"])
            self.assertEqual(stale_backoff["records"], ["old"])
            self.assertEqual(fetch.call_count, 2)

    def test_meals_cache_serves_stale_after_upstream_failure(self):
        with patch("backend.app.cache", Cache(ttl=0, retry_delay=60)), \
                patch.dict("os.environ", {"NEIS_API_KEY": "test-key"}), \
                patch("backend.app.NEISClient.from_environment") as factory:
            client = factory.return_value
            client.get_meals.side_effect = [
                [Meal("2026-11-10", "lunch", "rice(1)")],
                RuntimeError("upstream unavailable"),
            ]
            path = "/api/v1/meals?school=B10%3A1234567&from=2026-11-09&to=2026-11-15"

            self.assertFalse(self.get(path)["stale"])
            stale = self.get(path)
            backoff_stale = self.get(path)

            self.assertTrue(stale["stale"])
            self.assertEqual(stale["meals"][0]["dishes"], ["rice(1)"])
            self.assertTrue(backoff_stale["stale"])
            self.assertEqual(backoff_stale["meals"][0]["dishes"], ["rice(1)"])
            self.assertEqual(client.get_meals.call_count, 2)

    def test_meals_first_upstream_failure_returns_service_unavailable(self):
        with patch("backend.app.cache", Cache(retry_delay=60)), \
                patch.dict("os.environ", {"NEIS_API_KEY": "test-key"}), \
                patch("backend.app.NEISClient.from_environment") as factory:
            factory.return_value.get_meals.side_effect = RuntimeError("upstream unavailable")
            path = "/api/v1/meals?school=B10%3A1234567&from=2026-11-09&to=2026-11-15"

            for _ in range(2):
                with self.assertRaises(HTTPError) as error:
                    self.get(path)
                self.assertEqual(error.exception.code, 503)

            factory.return_value.get_meals.assert_called_once()

    def test_meals_and_timetable_use_distinct_cache_keys(self):
        test_cache = Cache()
        with patch("backend.app.cache", test_cache):
            test_cache.get(("timetable", "B10:1234567", "2026-11-09"), lambda: {"timetable": True})
            test_cache.get(("meals", "B10:1234567", "2026-11-09", "2026-11-15"), lambda: {"meals": []})

            self.assertEqual(len(test_cache.entries), 2)

    def test_invalid_inputs_and_upstream_failure(self):
        for path in ["/api/v1/schools?q=", "/api/v1/meals?school=invalid&from=2026-11-09&to=2026-11-15"]:
            with self.assertRaises(HTTPError) as error:
                self.get(path)
            self.assertEqual(error.exception.code, 400)
        with patch("backend.app.search_schools", side_effect=RuntimeError("secret details")):
            with self.assertRaises(HTTPError) as error:
                self.get("/api/v1/schools?q=school")
            self.assertEqual(error.exception.code, 503)
            self.assertNotIn("secret details", error.exception.read().decode())


if __name__ == "__main__":
    unittest.main()
