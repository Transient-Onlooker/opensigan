import asyncio
import sqlite3
import unittest
from pathlib import Path

from d1_cache import D1Cache


MIGRATION = Path(__file__).parent / "migrations" / "0001_request_rate_limit.sql"


class RequestRateLimitMigrationTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(
            """CREATE TABLE d1_cache (
                   cache_key TEXT PRIMARY KEY NOT NULL,
                   origin TEXT NOT NULL,
                   payload TEXT,
                   expires_at INTEGER NOT NULL DEFAULT 0,
                   refresh_owner TEXT,
                   lease_until INTEGER,
                   failures INTEGER NOT NULL DEFAULT 0 CHECK (failures >= 0),
                   retry_after INTEGER,
                   CHECK ((refresh_owner IS NULL) = (lease_until IS NULL))
               );
               CREATE INDEX d1_cache_expiry_idx ON d1_cache(expires_at);
               CREATE INDEX d1_cache_origin_active_lease_idx ON d1_cache(origin, lease_until)
                   WHERE refresh_owner IS NOT NULL;
               INSERT INTO d1_cache (cache_key, origin, payload, expires_at)
               VALUES ('existing', 'upstream', '{"ok":true}', 123);"""
        )

    def tearDown(self):
        self.db.close()

    def test_adds_nullable_rate_timestamp_and_partial_index_without_data_loss(self):
        self.db.executescript(MIGRATION.read_text(encoding="utf-8"))

        columns = {row[1]: row for row in self.db.execute("PRAGMA table_info(d1_cache)")}
        self.assertIn("last_refresh_at", columns)
        self.assertEqual(columns["last_refresh_at"][3], 0)
        self.assertEqual(
            self.db.execute(
                "SELECT origin, payload, expires_at, last_refresh_at FROM d1_cache WHERE cache_key = 'existing'"
            ).fetchone(),
            ("upstream", '{"ok":true}', 123, None),
        )

        indexes = {row[1]: row for row in self.db.execute("PRAGMA index_list(d1_cache)")}
        self.assertIn("d1_cache_origin_last_refresh_idx", indexes)
        self.assertEqual(indexes["d1_cache_origin_last_refresh_idx"][4], 1)

    def test_migration_is_one_time_and_reapplication_fails_clearly(self):
        migration = MIGRATION.read_text(encoding="utf-8")
        self.db.executescript(migration)
        with self.assertRaisesRegex(sqlite3.OperationalError, "duplicate column name"):
            self.db.executescript(migration)

    def test_migrated_database_enforces_origin_interval(self):
        self.db.executescript(MIGRATION.read_text(encoding="utf-8"))
        self.db.row_factory = sqlite3.Row
        db = self.db

        class Statement:
            def __init__(self, sql):
                self.sql = sql

            def bind(self, *params):
                self.params = params
                return self

            def first(self):
                row = db.execute(self.sql, self.params).fetchone()
                return dict(row) if row else None

        class Database:
            def prepare(self, sql):
                return Statement(sql)

        async def check():
            cache = D1Cache(Database(), min_origin_interval_seconds=2)
            self.assertTrue(await cache.acquire_refresh("a", "a", origin="upstream", now=10,
                                                        lease_seconds=5, rate_now_ms=10999))
            self.assertTrue(await cache.store_success("a", "a", {}, now=10, ttl_seconds=1))
            self.assertFalse(await cache.acquire_refresh("b", "b", origin="upstream", now=12,
                                                         lease_seconds=5, rate_now_ms=12998))
            self.assertTrue(await cache.acquire_refresh("b", "b", origin="upstream", now=12,
                                                        lease_seconds=5, rate_now_ms=12999))
            self.assertEqual((await cache.read("existing")).value, {"ok": True})

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
