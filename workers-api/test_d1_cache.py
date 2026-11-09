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
        self.assertTrue(await self.cache.acquire_refresh("k", "owner", now=100, lease_seconds=10))
        self.assertTrue(await self.cache.store_success("k", "owner", {"x": 1}, now=100, ttl_seconds=5))
        entry = await self.cache.read("k")
        self.assertTrue(entry.fresh(104))
        self.assertFalse(await self.cache.acquire_refresh("k", "another", now=104, lease_seconds=5))
        self.assertFalse(entry.fresh(105))
        self.assertTrue(entry.stale(105))

    async def test_expired_lease_fences_old_owner_and_allows_takeover(self):
        self.assertTrue(await self.cache.acquire_refresh("k", "old", now=100, lease_seconds=5))
        self.assertFalse(await self.cache.acquire_refresh("k", "other", now=102, lease_seconds=5))
        self.assertFalse(await self.cache.store_success("k", "old", {}, now=105, ttl_seconds=30))
        self.assertFalse(await self.cache.store_failure("k", "old", now=105))
        self.assertTrue(await self.cache.acquire_refresh("k", "new", now=105, lease_seconds=5))
        self.assertFalse(await self.cache.store_success("k", "old", {"old": True}, now=106, ttl_seconds=30))
        self.assertFalse(await self.cache.store_failure("k", "old", now=106))
        self.assertTrue(await self.cache.store_success("k", "new", {"new": True}, now=106, ttl_seconds=30))
        self.assertEqual((await self.cache.read("k")).value, {"new": True})

    async def test_concurrent_acquisition_has_one_winner_in_sqlite(self):
        barrier = threading.Barrier(8)
        outcomes = []

        def contend(index):
            barrier.wait()
            return asyncio.run(self.cache.acquire_refresh("race", f"owner-{index}", now=200,
                                                          lease_seconds=20))

        threads = [threading.Thread(target=lambda i=i: outcomes.append(contend(i))) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(outcomes), 8)
        self.assertEqual(sum(outcomes), 1)

    async def test_failure_backoff_preserves_stale_payload_and_then_releases(self):
        self.assertTrue(await self.cache.acquire_refresh("k", "a", now=1, lease_seconds=5))
        self.assertTrue(await self.cache.store_success("k", "a", {"cached": True}, now=1, ttl_seconds=1))
        self.assertTrue(await self.cache.acquire_refresh("k", "b", now=2, lease_seconds=5))
        self.assertTrue(await self.cache.store_failure("k", "b", now=2))
        entry = await self.cache.read("k")
        self.assertEqual(entry.value, {"cached": True})
        self.assertEqual(entry.retry_after, 7)
        self.assertFalse(await self.cache.acquire_refresh("k", "c", now=6, lease_seconds=5))
        self.assertTrue(await self.cache.acquire_refresh("k", "c", now=7, lease_seconds=5))
        self.assertTrue(await self.cache.store_failure("k", "c", now=7))
        self.assertEqual((await self.cache.read("k")).retry_after, 17)
        self.assertTrue(await self.cache.acquire_refresh("k", "d", now=17, lease_seconds=5))
        self.assertTrue(await self.cache.store_success("k", "d", None, now=17, ttl_seconds=5))
        entry = await self.cache.read("k")
        self.assertTrue(entry.fresh(18))
        self.assertIsNone(entry.value)
        self.assertEqual((entry.failures, entry.retry_after), (0, None))

    async def test_mock_d1_adapter_uses_same_sql_contract(self):
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        adapter = MockD1(schema, str(Path(self.temp.name) / "mock.sqlite"))
        cache = D1Cache(adapter)
        self.assertTrue(await cache.acquire_refresh("school:week", "token", now=50, lease_seconds=10))
        self.assertTrue(await cache.store_success("school:week", "token", {"rows": []}, now=50, ttl_seconds=60))
        self.assertEqual((await cache.read("school:week")).value, {"rows": []})
        self.assertEqual(len(adapter.calls), 3)

    async def test_cold_failure_backoff_is_capped(self):
        cache = D1Cache(self.sqlite_db, base_backoff_seconds=2, max_backoff_seconds=3)
        self.assertIsNone(await cache.read("cold"))
        self.assertTrue(await cache.acquire_refresh("cold", "a", now=10, lease_seconds=5))
        self.assertTrue(await cache.store_failure("cold", "a", now=10))
        self.assertFalse((await cache.read("cold")).stale(10))
        self.assertTrue(await cache.acquire_refresh("cold", "b", now=12, lease_seconds=5))
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
