import asyncio
import os
from contextlib import closing
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
import d1_cache
D1Cache = d1_cache.D1Cache


class SQLiteStatement:
    def __init__(self, db, sql):
        self.db, self.sql, self.params = db, sql, ()

    def bind(self, *params):
        self.params = params
        return self

    async def first(self):
        with closing(self.db.connect()) as connection:
            cursor = connection.execute(self.sql, self.params)
            row = cursor.fetchone()
            cursor.close()
            return dict(row) if row else None

    async def run(self):
        with closing(self.db.connect()) as connection:
            cursor = connection.execute(self.sql, self.params)
            return {"meta": {"changes": cursor.rowcount}}


class SQLiteD1:
    def __init__(self, schema, path):
        self.path = path
        with closing(self.connect()) as connection:
            connection.executescript(schema)

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        return connection

    def prepare(self, sql):
        return SQLiteStatement(self, sql)


class MockStatement:
    def __init__(self, adapter, sql):
        self.adapter, self.sql, self.params = adapter, sql, ()

    def bind(self, *params):
        self.params = params
        return self

    async def first(self):
        return self.adapter.execute(self.sql, self.params, first=True)

    async def run(self):
        return self.adapter.execute(self.sql, self.params, first=False)


class MockD1:
    """D1-shaped adapter that delegates SQL semantics to SQLite."""
    def __init__(self, schema, path):
        self.db = SQLiteD1(schema, path)
        self.calls = []

    def prepare(self, sql):
        return MockStatement(self, sql)

    def execute(self, sql, params, *, first):
        self.calls.append((sql, params, first))
        with closing(self.db.connect()) as connection:
            cursor = connection.execute(sql, params)
            row = cursor.fetchone() if first else None
            cursor.close()
            return dict(row) if row else None


class D1CacheTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        temp_dir = Path.home() / "AppData" / "Local" / "Temp" if os.name == "nt" else None
        self.temp = tempfile.TemporaryDirectory(dir=temp_dir)
        self.addCleanup(self.temp.cleanup)
        self.sqlite_db = SQLiteD1(schema, str(Path(self.temp.name) / "cache.sqlite"))
        self.cache = D1Cache(self.sqlite_db)

    async def test_stale_value_available_while_refresh_lease_is_held(self):
        self.assertTrue(await self.cache.acquire_refresh("k", "owner", origin="test", now=100, lease_seconds=10))
        self.assertTrue(await self.cache.store_success("k", "owner", {"x": 1}, now=100, ttl_seconds=5))
        entry = await self.cache.read("k")
        self.assertTrue(entry.fresh(104))
        self.assertFalse(await self.cache.acquire_refresh("k", "another", origin="test", now=104, lease_seconds=5))
        self.assertFalse(entry.fresh(105))
        self.assertTrue(entry.stale(105))

    async def test_expired_lease_fences_old_owner_and_allows_takeover(self):
        self.assertTrue(await self.cache.acquire_refresh("k", "old", origin="test", now=100, lease_seconds=5))
        self.assertFalse(await self.cache.acquire_refresh("k", "other", origin="test", now=102, lease_seconds=5))
        self.assertFalse(await self.cache.store_success("k", "old", {}, now=105, ttl_seconds=30))
        self.assertFalse(await self.cache.store_failure("k", "old", now=105))
        self.assertTrue(await self.cache.acquire_refresh("k", "new", origin="test", now=105, lease_seconds=5))
        self.assertFalse(await self.cache.store_success("k", "old", {"old": True}, now=106, ttl_seconds=30))
        self.assertFalse(await self.cache.store_failure("k", "old", now=106))
        self.assertTrue(await self.cache.store_success("k", "new", {"new": True}, now=106, ttl_seconds=30))
        self.assertEqual((await self.cache.read("k")).value, {"new": True})

    async def test_concurrent_acquisition_has_one_winner_in_sqlite(self):
        barrier = threading.Barrier(8)
        outcomes = []

        def contend(index):
            barrier.wait()
            return asyncio.run(self.cache.acquire_refresh("race", f"owner-{index}", origin="test", now=200,
                                                          lease_seconds=20))

        threads = [threading.Thread(target=lambda i=i: outcomes.append(contend(i))) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(outcomes), 8)
        self.assertEqual(sum(outcomes), 1)

    async def test_distinct_arbitrary_keys_contend_for_one_origin_slot(self):
        barrier = threading.Barrier(10)
        outcomes = []

        def contend(index):
            key = f"arbitrary-{index}"
            barrier.wait()
            return asyncio.run(self.cache.acquire_refresh(key, f"owner-{index}", origin="comcigan", now=200,
                                                          lease_seconds=20))

        threads = [threading.Thread(target=lambda i=i: outcomes.append(contend(i))) for i in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(outcomes), 10)
        self.assertEqual(sum(outcomes), 1)

    async def test_origin_interval_survives_release_and_failure_at_millisecond_boundary(self):
        cache = D1Cache(self.sqlite_db, min_origin_interval_seconds=2)
        self.assertTrue(await cache.acquire_refresh("a", "a", origin="one", now=10, lease_seconds=5, rate_now_ms=10999))
        self.assertTrue(await cache.store_success("a", "a", {"cached": True}, now=10, ttl_seconds=1))
        self.assertFalse(await cache.acquire_refresh("b", "b", origin="one", now=12, lease_seconds=5, rate_now_ms=12998))
        self.assertTrue(await cache.acquire_refresh("other", "o", origin="two", now=12, lease_seconds=5, rate_now_ms=12998))
        self.assertTrue(await cache.acquire_refresh("b", "b", origin="one", now=12, lease_seconds=5, rate_now_ms=12999))
        self.assertTrue(await cache.store_failure("b", "b", now=12))
        self.assertFalse(await cache.acquire_refresh("c", "c", origin="one", now=14, lease_seconds=5, rate_now_ms=14998))
        self.assertTrue(await cache.acquire_refresh("c", "c", origin="one", now=14, lease_seconds=5, rate_now_ms=14999))
        self.assertEqual((await cache.read("a")).value, {"cached": True})

    async def test_denied_fresh_key_does_not_consume_origin_interval(self):
        cache = D1Cache(self.sqlite_db, min_origin_interval_seconds=2)
        self.assertTrue(await cache.acquire_refresh("fresh", "a", origin="one", now=10, lease_seconds=5))
        self.assertTrue(await cache.store_success("fresh", "a", {}, now=10, ttl_seconds=100))
        self.assertFalse(await cache.acquire_refresh("fresh", "b", origin="one", now=12, lease_seconds=5))
        self.assertTrue(await cache.acquire_refresh("cold", "c", origin="one", now=12, lease_seconds=5))

    async def test_concurrent_fast_refreshes_cannot_bypass_origin_interval(self):
        barrier = threading.Barrier(8)
        outcomes = []

        async def refresh(index):
            key = f"fast-{index}"
            won = await self.cache.acquire_refresh(key, key, origin="test", now=100, lease_seconds=5)
            if won:
                await self.cache.store_success(key, key, {}, now=100, ttl_seconds=5)
            return won

        def contend(index):
            barrier.wait()
            outcomes.append(asyncio.run(refresh(index)))

        threads = [threading.Thread(target=contend, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(outcomes), 8)
        self.assertEqual(sum(outcomes), 1)

    async def test_origin_is_required_and_a_key_cannot_change_origins(self):
        with self.assertRaises(ValueError):
            await self.cache.acquire_refresh("k", "a", origin=" ", now=1, lease_seconds=5)
        self.assertTrue(await self.cache.acquire_refresh("k", "a", origin="one", now=1, lease_seconds=5))
        self.assertTrue(await self.cache.store_failure("k", "a", now=1))
        self.assertFalse(await self.cache.acquire_refresh("k", "b", origin="two", now=6, lease_seconds=5))
        self.assertTrue(await self.cache.acquire_refresh("k", "b", origin="one", now=6, lease_seconds=5))

    async def test_origin_slots_are_independent_and_release_on_success_or_failure(self):
        school = 'opensigan:["schools","a"]'
        timetable = 'opensigan:["timetable","1:a","2026-11-09"]'
        neis = 'opensigan:["neis-schools","a"]'
        meals = 'opensigan:["meals","A01:1234567","2026-11-09","2026-11-09"]'
        self.assertTrue(await self.cache.acquire_refresh(school, "a", origin="comcigan", now=10, lease_seconds=20))
        self.assertTrue(await self.cache.acquire_refresh(neis, "b", origin="neis", now=10, lease_seconds=20))
        self.assertFalse(await self.cache.acquire_refresh(timetable, "c", origin="comcigan", now=10, lease_seconds=20))
        self.assertFalse(await self.cache.acquire_refresh(meals, "d", origin="neis", now=10, lease_seconds=20))
        self.assertTrue(await self.cache.store_success(school, "a", {"old": 1}, now=10, ttl_seconds=1))
        self.assertTrue(await self.cache.acquire_refresh(timetable, "c", origin="comcigan", now=11, lease_seconds=20))
        self.assertTrue(await self.cache.store_failure(neis, "b", now=11))
        self.assertTrue(await self.cache.acquire_refresh(meals, "d", origin="neis", now=11, lease_seconds=20))
        self.assertFalse(await self.cache.acquire_refresh(school, "e", origin="comcigan", now=11, lease_seconds=20))
        self.assertEqual((await self.cache.read(school)).value, {"old": 1})
        self.assertIsNone((await self.cache.read(school)).retry_after)
        self.assertTrue(await self.cache.store_failure(timetable, "c", now=12))
        self.assertTrue(await self.cache.acquire_refresh(school, "e", origin="comcigan", now=12, lease_seconds=20))

    async def test_expired_origin_slot_allows_takeover_but_fences_old_owner(self):
        old = 'opensigan:["timetable","1:a","2026-11-09"]'
        new = 'opensigan:["schools","b"]'
        self.assertTrue(await self.cache.acquire_refresh(old, "a", origin="comcigan", now=100, lease_seconds=5))
        self.assertFalse(await self.cache.acquire_refresh(new, "b", origin="comcigan", now=104, lease_seconds=5))
        self.assertTrue(await self.cache.acquire_refresh(new, "b", origin="comcigan", now=105, lease_seconds=5))
        self.assertFalse(await self.cache.store_success(old, "a", {}, now=105, ttl_seconds=5))
        self.assertFalse(await self.cache.store_failure(old, "a", now=105))
        self.assertFalse(await self.cache.acquire_refresh(old, "c", origin="comcigan", now=105, lease_seconds=5))

    async def test_failure_backoff_preserves_stale_payload_and_then_releases(self):
        self.assertTrue(await self.cache.acquire_refresh("k", "a", origin="test", now=1, lease_seconds=5))
        self.assertTrue(await self.cache.store_success("k", "a", {"cached": True}, now=1, ttl_seconds=1))
        self.assertTrue(await self.cache.acquire_refresh("k", "b", origin="test", now=2, lease_seconds=5))
        self.assertTrue(await self.cache.store_failure("k", "b", now=2))
        entry = await self.cache.read("k")
        self.assertEqual(entry.value, {"cached": True})
        self.assertEqual(entry.retry_after, 7)
        self.assertFalse(await self.cache.acquire_refresh("k", "c", origin="test", now=6, lease_seconds=5))
        self.assertTrue(await self.cache.acquire_refresh("k", "c", origin="test", now=7, lease_seconds=5))
        self.assertTrue(await self.cache.store_failure("k", "c", now=7))
        self.assertEqual((await self.cache.read("k")).retry_after, 17)
        self.assertTrue(await self.cache.acquire_refresh("k", "d", origin="test", now=17, lease_seconds=5))
        self.assertTrue(await self.cache.store_success("k", "d", None, now=17, ttl_seconds=5))
        entry = await self.cache.read("k")
        self.assertTrue(entry.fresh(18))
        self.assertIsNone(entry.value)
        self.assertEqual((entry.failures, entry.retry_after), (0, None))

    async def test_mock_d1_adapter_uses_same_sql_contract(self):
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        adapter = MockD1(schema, str(Path(self.temp.name) / "mock.sqlite"))
        cache = D1Cache(adapter)
        self.assertTrue(await cache.acquire_refresh("school:week", "token", origin="test", now=50, lease_seconds=10))
        self.assertTrue(await cache.store_success("school:week", "token", {"rows": []}, now=50, ttl_seconds=60))
        self.assertEqual((await cache.read("school:week")).value, {"rows": []})
        self.assertEqual(len(adapter.calls), 3)

    async def test_cold_failure_backoff_is_capped(self):
        cache = D1Cache(self.sqlite_db, base_backoff_seconds=2, max_backoff_seconds=3)
        self.assertIsNone(await cache.read("cold"))
        self.assertTrue(await cache.acquire_refresh("cold", "a", origin="test", now=10, lease_seconds=5))
        self.assertTrue(await cache.store_failure("cold", "a", now=10))
        self.assertFalse((await cache.read("cold")).stale(10))
        self.assertTrue(await cache.acquire_refresh("cold", "b", origin="test", now=12, lease_seconds=5))
        self.assertTrue(await cache.store_failure("cold", "b", now=12))
        self.assertEqual((await cache.read("cold")).retry_after, 15)

    async def test_school_week_key(self):
        self.assertEqual(d1_cache.school_week_key("123:school", "2026-11-09"),
                         'timetable:["123:school","2026-11-09"]')
        self.assertNotEqual(d1_cache.school_week_key("a:b", "c"),
                            d1_cache.school_week_key("a", "b:c"))
        with self.assertRaises(ValueError):
            d1_cache.school_week_key("", "2026-11-09")


if __name__ == "__main__":
    unittest.main()
