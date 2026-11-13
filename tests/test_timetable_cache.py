import threading
import unittest
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import urlencode
from urllib.request import urlopen

from backend import cache as cache_module
from backend import timetable


class FakeLesson:
    def __init__(self, period, subject="", teacher="", replaced=False):
        self.period = period
        self.subject = subject
        self.teacher = teacher
        self.replaced = replaced


class TimetableTests(unittest.TestCase):
    def test_403_invalidates_without_immediate_retry(self):
        from types import SimpleNamespace
        timetable._protocol = None
        timetable._protocol_expires = 0
        with patch('pycomcigan.helpers.get_comcigan_response_for_codes', return_value=SimpleNamespace(text='page')) as page, \
             patch('pycomcigan.service_page.decode_service_page', return_value='decoded'), \
             patch('pycomcigan.service_protocol.parse_service_protocol', side_effect=[SimpleNamespace(endpoint='/old'), SimpleNamespace(endpoint='/new')]), \
             patch('pycomcigan.helpers.school_search', side_effect=[RuntimeError('Comcigan request rejected (HTTP 403); the page token may have expired'), []]) as search:
            with self.assertRaisesRegex(RuntimeError, '403'):
                timetable._search_with_cached_protocol('one')
            self.assertEqual(page.call_count, 1)
            self.assertEqual(search.call_count, 1)
            self.assertEqual(timetable._search_with_cached_protocol('two'), [])
            self.assertEqual(page.call_count, 2)
        timetable._protocol = None
        timetable._protocol_expires = 0

    def test_protocol_reuse_refresh_and_no_retry_for_rate_limit(self):
        from types import SimpleNamespace
        protocols = [SimpleNamespace(endpoint='/old'), SimpleNamespace(endpoint='/new')]
        timetable._protocol = None
        timetable._protocol_expires = 0
        with patch('pycomcigan.helpers.get_comcigan_response_for_codes', return_value=SimpleNamespace(text='page')) as page, \
             patch('pycomcigan.service_page.decode_service_page', return_value='decoded'), \
             patch('pycomcigan.service_protocol.parse_service_protocol', side_effect=protocols) as parse, \
             patch('pycomcigan.helpers.school_search', side_effect=[[], [], RuntimeError('Encrypted response authentication failed'), [], RuntimeError('Comcigan rate limit reached (HTTP 429); retry later')]) as search:
            self.assertEqual(timetable._search_with_cached_protocol('one'), [])
            self.assertEqual(timetable._search_with_cached_protocol('two'), [])
            self.assertEqual(page.call_count, 1)
            self.assertEqual(timetable._search_with_cached_protocol('three'), [])
            self.assertEqual(page.call_count, 2)
            with self.assertRaisesRegex(RuntimeError, '429'):
                timetable._search_with_cached_protocol('four')
            self.assertEqual(page.call_count, 2)
            self.assertEqual(search.call_count, 5)
            self.assertEqual(parse.call_count, 2)
        timetable._protocol = None
        timetable._protocol_expires = 0

    def test_seven_day_source_keeps_weekday_records(self):
        days = [[], [FakeLesson(1, "Math", "Kim")], [], [], [], [], [], []]
        table = type("Table", (), {"timetable": [[], [[], days]], "update_date": None})()
        result, _ = self.fetch_with("2026-11-09", table)
        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(result["records"][0]["date"], "2026-11-09")

    def fetch_with(self, week, table, today=(2026, 11, 10)):
        fixed_datetime = type("FixedDateTime", (datetime,), {
            "now": classmethod(lambda cls, tz=None: datetime(*today, tzinfo=tz))
        })
        with patch("backend.timetable.datetime", fixed_datetime), patch(
            "pycomcigan.TimeTable", return_value=table
        ) as constructor:
            result = timetable.fetch_timetable("2:Example", week)
        return result, constructor

    def test_indexes_records_and_preserves_change_metadata(self):
        table = type("Table", (), {
            "timetable": [[], [[], [
                [FakeLesson(0, "ignored", "", False)],
                [FakeLesson(1, "Math", "Kim"), FakeLesson(2, "", "", True), FakeLesson(3)],
                [], [], [], [FakeLesson(4, "Art", "Park")], [FakeLesson(7, "weekend", "")],
            ], [
                [FakeLesson(0)], [FakeLesson(1, "Science", "Lee")], [], [], [], [], [],
            ]]],
            "update_date": "2026-11-10 08:30",
        })()

        result, constructor = self.fetch_with("2026-11-09", table)

        self.assertEqual(constructor.call_args.kwargs, {
            "school_code": 2, "week_num": 0,
        })
        self.assertEqual(result["records"], [
            {"grade": 1, "class": 1, "date": "2026-11-09", "period": 1,
             "subject": "Math", "teacher": "Kim", "isChanged": False},
            {"grade": 1, "class": 1, "date": "2026-11-09", "period": 2,
             "subject": "", "teacher": "", "isChanged": True},
            {"grade": 1, "class": 1, "date": "2026-11-13", "period": 4,
             "subject": "Art", "teacher": "Park", "isChanged": False},
            {"grade": 1, "class": 2, "date": "2026-11-09", "period": 1,
             "subject": "Science", "teacher": "Lee", "isChanged": False},
        ])
        self.assertEqual(result["sourceUpdatedAt"], "2026-11-10T08:30:00+09:00")
        self.assertEqual(result["fetchedAt"], "2026-11-10T00:00:00+00:00")
        self.assertFalse(result["stale"])

    def test_accepts_current_and_next_week_and_rejects_other_starts(self):
        empty = type("Table", (), {"timetable": [], "update_date": None})()
        for week, expected_offset in [("2026-11-09", 0), ("2026-11-16", 1)]:
            with self.subTest(week=week):
                _, constructor = self.fetch_with(week, empty)
                self.assertEqual(constructor.call_args.kwargs["week_num"], expected_offset)
        for week in ["2026-11-10", "2026-11-02", "2026-11-23"]:
            with self.subTest(week=week), self.assertRaises(ValueError):
                self.fetch_with(week, empty)

    def test_source_updated_at_uses_korean_timezone(self):
        for source, expected in [("2026-11-09 10:28:08", "2026-11-09T10:28:08+09:00"),
                                 ("2026-11-09T01:28:08+00:00", "2026-11-09T10:28:08+09:00")]:
            table = type("Table", (), {"timetable": [], "update_date": source})()
            with self.subTest(source=source):
                result, _ = self.fetch_with("2026-11-09", table)
                self.assertEqual(result["sourceUpdatedAt"], expected)
        table = type("Table", (), {"timetable": [], "update_date": "invalid"})()
        with self.assertRaises(RuntimeError):
            self.fetch_with("2026-11-09", table)

    def test_sunday_to_monday_changes_current_week_across_year(self):
        empty = type("Table", (), {"timetable": [], "update_date": None})()
        _, sunday = self.fetch_with("2026-12-28", empty, (2026, 12, 27))
        _, monday = self.fetch_with("2026-12-28", empty, (2026, 12, 28))
        _, new_year = self.fetch_with("2027-01-04", empty, (2026, 12, 28))
        self.assertEqual([sunday.call_args.kwargs["week_num"],
                          monday.call_args.kwargs["week_num"],
                          new_year.call_args.kwargs["week_num"]], [1, 0, 1])

    def test_korean_midnight_changes_week_before_utc(self):
        instant = datetime(2026, 12, 27, 14, 59, tzinfo=timezone.utc)
        fixed = type("FixedDateTime", (datetime,), {
            "now": classmethod(lambda cls, tz=None: instant.astimezone(tz))
        })
        with patch("backend.timetable.datetime", fixed):
            self.assertEqual(timetable.validate_timetable_week("2026-12-21"), 0)
            self.assertEqual(timetable.validate_timetable_week("2026-12-28"), 1)
            instant = datetime(2026, 12, 27, 15, 0, tzinfo=timezone.utc)
            with self.assertRaises(ValueError):
                timetable.validate_timetable_week("2026-12-21")
            self.assertEqual(timetable.validate_timetable_week("2026-12-28"), 0)
            self.assertEqual(timetable.validate_timetable_week("2027-01-04"), 1)

    def test_rotating_region_and_duplicate_names_use_school_code(self):
        from pycomcigan import TimeTable

        empty = type("Table", (), {"timetable": [], "update_date": None})()
        rows = [[9999, "region A", "Example", 76524],
                [6347, "region B", "Example", 76525]]

        def construct(name, **kwargs):
            selected = TimeTable._resolve_school(None, name, kwargs.get("local_code", 0),
                                                 kwargs["school_code"], "endpoint")
            self.assertEqual(selected, (9999, "Example", 76524))
            return empty

        fixed = type("FixedDateTime", (datetime,), {
            "now": classmethod(lambda cls, tz=None: datetime(2026, 11, 10, tzinfo=tz))
        })
        with patch("backend.timetable.datetime", fixed), patch(
            "pycomcigan.timetable.school_search", return_value=rows
        ), patch("pycomcigan.TimeTable", side_effect=construct):
            result = timetable.fetch_timetable("76524:Example", "2026-11-09")
        self.assertEqual(result["schoolId"], "76524:Example")

    def test_duplicate_school_code_is_rejected_by_library(self):
        from pycomcigan import TimeTable

        rows = [[1, "A", "Example", 76524], [2, "B", "Example", 76524]]
        def construct(name, **kwargs):
            return TimeTable._resolve_school(None, name, kwargs.get("local_code", 0),
                                             kwargs["school_code"], "endpoint")
        fixed = type("FixedDateTime", (datetime,), {
            "now": classmethod(lambda cls, tz=None: datetime(2026, 11, 10, tzinfo=tz))
        })
        with patch("backend.timetable.datetime", fixed), patch(
            "pycomcigan.timetable.school_search", return_value=rows
        ), patch("pycomcigan.TimeTable", side_effect=construct):
            with self.assertRaisesRegex(RuntimeError, "Multiple schools"):
                timetable.fetch_timetable("76524:Example", "2026-11-09")

    def test_search_id_is_stable_across_region_code_changes(self):
        rows = [[6347, "region A", "Example", 76524],
                [1234, "region B", "Example", 76525]]
        with patch("backend.timetable._search_with_cached_protocol", return_value=rows):
            first = timetable.search_schools("Example")
        rows[0][0] = 9999
        with patch("backend.timetable._search_with_cached_protocol", return_value=rows):
            second = timetable.search_schools("Example")
        self.assertEqual(first, second)
        self.assertEqual(first, [{"id": "76524:Example", "name": "Example", "region": "region A"},
                                 {"id": "76525:Example", "name": "Example", "region": "region B"}])

    def test_malformed_school_search_response_is_rejected(self):
        for row in ([1, "region", "Example", 0], [1, "region", "bad:name", 2], [1]):
            with self.subTest(row=row), patch("backend.timetable._search_with_cached_protocol", return_value=[row]):
                with self.assertRaises(RuntimeError):
                    timetable.search_schools("Example")

    def test_http_search_then_timetable_with_rotated_region(self):
        from backend.app import Handler
        from pycomcigan import TimeTable

        rows = [[9999, "region", "Example", 76524],
                [6347, "other", "Example", 76525]]
        empty = type("Table", (), {"timetable": [], "update_date": None})()
        def construct(name, **kwargs):
            resolved = TimeTable._resolve_school(None, name, kwargs.get("local_code", 0),
                                                 kwargs["school_code"], "endpoint")
            self.assertEqual(resolved, (9999, "Example", 76524))
            return empty
        fixed = type("FixedDateTime", (datetime,), {
            "now": classmethod(lambda cls, tz=None: datetime(2026, 11, 10, tzinfo=tz))
        })
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with patch("backend.app.cache", cache_module.Cache()), patch(
                "backend.timetable.datetime", fixed
            ), patch("backend.timetable._search_with_cached_protocol", return_value=[[6347, "region", "Example", 76524]]), patch(
                "pycomcigan.timetable.school_search", return_value=rows
            ), patch("pycomcigan.TimeTable", side_effect=construct):
                with urlopen(base + "/api/v1/schools?q=Example") as response:
                    school_id = json.load(response)["schools"][0]["id"]
                query = urlencode({"school": school_id, "week": "2026-11-09"})
                with urlopen(base + "/api/v1/timetable?" + query) as response:
                    result = json.load(response)
                self.assertEqual(result["schoolId"], "76524:Example")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_invalid_identifiers_and_malformed_lessons_are_rejected(self):
        for school_id in ("0:Example", "2:", "2:bad:name", "x:Example", "1:2:Example"):
            with self.subTest(school_id=school_id), self.assertRaises(ValueError):
                timetable.fetch_timetable(school_id, "2026-11-09")
        table = type("Table", (), {"timetable": [[], [[], [[], [object()]]]],
                                   "update_date": None})()
        with self.assertRaises(RuntimeError):
            self.fetch_with("2026-11-09", table)

    def test_invalid_source_indexes_do_not_replace_cached_timetable(self):
        lesson = FakeLesson(1, "Math", "Kim")
        good = type("Table", (), {
            "timetable": [[], [[], [[], [lesson]]]], "update_date": None,
        })()
        malformed = [
            [[[[], [lesson]]]],
            [[], [[[], [lesson]]]],
            [[], [[], [[], [FakeLesson(0, "Math", "Kim")]]]],
        ]
        for data in malformed:
            with self.subTest(data=data):
                cache = cache_module.Cache(ttl=0, retry_delay=0)
                old = cache.get("week", lambda: self.fetch_with("2026-11-09", good)[0])
                bad = type("Table", (), {"timetable": data, "update_date": None})()
                with self.assertRaises(RuntimeError):
                    self.fetch_with("2026-11-09", bad)
                stale = cache.get("week", lambda: self.fetch_with("2026-11-09", bad)[0])
                self.assertEqual(stale, {**old, "stale": True})
                self.assertEqual(cache.get("week", lambda: self.fetch_with("2026-11-09", good)[0]), old)


class CacheTests(unittest.TestCase):
    def test_concurrent_misses_share_one_fetch(self):
        cache = cache_module.Cache(ttl=60)
        started = threading.Event()
        release = threading.Event()
        ready = threading.Barrier(8)
        calls = []
        value = {"records": [1], "stale": False}

        def fetch():
            calls.append(1)
            started.set()
            self.assertTrue(release.wait(2))
            return value

        def get():
            ready.wait(timeout=2)
            return cache.get("week", fetch)

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(get) for _ in range(8)]
            self.assertTrue(started.wait(2))
            release.set()
            results = [future.result(timeout=2) for future in futures]

        self.assertEqual(len(calls), 1)
        self.assertEqual(results, [value] * 8)

    def test_failed_refresh_returns_cached_data_as_stale(self):
        cache = cache_module.Cache(ttl=0, retry_delay=0)
        value = {"records": ["old"], "stale": False}
        self.assertEqual(cache.get("week", lambda: value), value)

        def fail():
            raise RuntimeError("upstream unavailable")

        self.assertEqual(cache.get("week", fail), {"records": ["old"], "stale": True})
        self.assertEqual(value, {"records": ["old"], "stale": False})
        self.assertEqual(cache.get("week", lambda: {"records": ["new"], "stale": False}),
                         {"records": ["new"], "stale": False})

    def test_failure_without_cached_data_propagates_and_can_retry(self):
        cache = cache_module.Cache(retry_delay=0)

        def fail():
            raise RuntimeError("upstream unavailable")

        with self.assertRaisesRegex(RuntimeError, "upstream unavailable"):
            cache.get("week", fail)
        self.assertEqual(cache.get("week", lambda: {"records": [], "stale": False}),
                         {"records": [], "stale": False})

    def test_nested_values_are_isolated_on_every_return(self):
        cache = cache_module.Cache(ttl=60)
        source = {"records": [{"subject": "Math"}], "stale": False}
        first = cache.get("week", lambda: source)
        source["records"][0]["subject"] = "source changed"
        first["records"][0]["subject"] = "client changed"
        self.assertEqual(cache.get("week", lambda: None)["records"][0]["subject"], "Math")

    def test_failure_backoff_applies_without_cached_data(self):
        cache = cache_module.Cache(retry_delay=60)
        calls = []
        def fail():
            calls.append(1)
            raise RuntimeError("unavailable")
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            cache.get("week", fail)
        with self.assertRaisesRegex(RuntimeError, "backoff"):
            cache.get("week", fail)
        self.assertEqual(len(calls), 1)

    def test_retry_after_backoff_and_invalid_payload_returns_stale(self):
        cache = cache_module.Cache(ttl=0, retry_delay=10)
        with patch("backend.cache.time.monotonic", return_value=100) as clock:
            cache.get("week", lambda: {"records": ["old"]})
            self.assertTrue(cache.get("week", lambda: {"records": [object()]})["stale"])
            clock.return_value = 109
            self.assertEqual(cache.get("week", lambda: self.fail("backoff ignored"))["records"], ["old"])
            clock.return_value = 110
            self.assertEqual(cache.get("week", lambda: {"records": ["new"]})["records"], ["new"])

    def test_distinct_stripes_fetch_concurrently(self):
        cache = cache_module.Cache(lock_stripes=2)
        started = threading.Barrier(2)
        def fetch():
            started.wait(timeout=2)
            return {"records": []}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(cache.get, key, fetch) for key in (0, 1)]
            for future in futures:
                self.assertEqual(future.result(timeout=3), {"records": []})

    def test_cache_hit_not_blocked_by_concurrent_fetch_on_same_stripe(self):
        cache = cache_module.Cache(ttl=60, lock_stripes=1)
        cache.get("cached_key", lambda: {"records": [1], "stale": False})
        started = threading.Event()
        release = threading.Event()
        def slow_fetch():
            started.set()
            if not release.wait(2):
                raise RuntimeError("slow fetch timed out")
            return {"records": [2], "stale": False}
        with ThreadPoolExecutor(max_workers=2) as pool:
            fetch_future = pool.submit(cache.get, "miss_key", slow_fetch)
            self.assertTrue(started.wait(2))
            try:
                hit_future = pool.submit(cache.get, "cached_key", lambda: None)
                self.assertEqual(hit_future.result(timeout=0.5), {"records": [1], "stale": False})
            finally:
                release.set()
                self.assertEqual(fetch_future.result(timeout=2), {"records": [2], "stale": False})

    def test_stale_backoff_and_cache_limits(self):
        cache = cache_module.Cache(ttl=0, retry_delay=60, max_entries=2, max_bytes=100)
        cache.get("a", lambda: {"records": ["old"], "stale": False})
        def fail():
            raise RuntimeError("unavailable")
        stale = cache.get("a", fail)
        stale["records"].append("changed")
        self.assertEqual(cache.get("a", lambda: self.fail("backoff ignored"))["records"], ["old"])
        cache.get("b", lambda: {"records": []})
        cache.get("c", lambda: {"records": []})
        self.assertLessEqual(len(cache.entries), 2)
        self.assertLessEqual(cache.bytes_used, 100)
        self.assertNotIn("a", cache.entries)
        cache.get("big", lambda: {"records": ["x" * 200]})
        self.assertNotIn("big", cache.entries)
        self.assertLessEqual(cache.bytes_used, 100)


if __name__ == "__main__":
    unittest.main()
