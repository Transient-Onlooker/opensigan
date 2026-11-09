"""A small D1-backed stale-while-revalidate cache.

The module does not call upstream services. Callers read, optionally acquire a
refresh lease, then store success/failure with the lease owner's opaque token.
Choose lease_seconds to exceed the caller's full upstream request budget,
including retries and scheduling delay. This module does not renew leases.
An expired lease can be taken over; the old owner is fenced from committing,
but can still waste upstream work. SQLite tests and mock D1 adapters validate
the SQL contract, not Cloudflare's distributed consistency/transaction
behavior; that needs separate D1 validation.
Use a new random owner token for every attempt and obtain UTC time immediately
before each operation; clock skew or delayed SQL execution can affect expiry.
When no stale value exists, callers choose their own unavailable/backoff response.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CacheEntry:
    value: Any | None
    has_value: bool
    expires_at: int
    retry_after: int | None
    failures: int

    def fresh(self, now: int) -> bool:
        return self.has_value and self.expires_at > now

    def stale(self, now: int) -> bool:
        return self.has_value and self.expires_at <= now


async def _await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class D1Cache:
    """D1 API compatible cache. Timestamps are Unix seconds from the caller."""

    def __init__(self, database: Any, *, base_backoff_seconds: int = 5,
                 max_backoff_seconds: int = 300):
        if base_backoff_seconds < 1 or max_backoff_seconds < base_backoff_seconds:
            raise ValueError("invalid backoff bounds")
        self.database = database
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds

    async def _first(self, sql: str, *params: Any) -> Any:
        statement = self.database.prepare(sql).bind(*params)
        row = await _await(statement.first())
        return row.to_py() if row is not None and hasattr(row, "to_py") else row

    async def read(self, key: str) -> CacheEntry | None:
        row = await self._first(
            "SELECT payload, expires_at, retry_after, failures FROM d1_cache WHERE cache_key = ?",
            key,
        )
        if row is None:
            return None
        payload = row.get("payload")
        return CacheEntry(json.loads(payload) if payload is not None else None, payload is not None,
                          int(row["expires_at"]),
                          int(row["retry_after"]) if row.get("retry_after") is not None else None,
                          int(row["failures"]))

    async def acquire_refresh(self, key: str, owner_token: str, *, now: int,
                              lease_seconds: int) -> bool:
        if not key or not owner_token or lease_seconds < 1:
            raise ValueError("key, owner token, and positive lease are required")
        row = await self._first(
            """INSERT INTO d1_cache
                   (cache_key, payload, expires_at, refresh_owner, lease_until, failures, retry_after)
               VALUES (?, NULL, 0, ?, ?, 0, NULL)
               ON CONFLICT(cache_key) DO UPDATE SET
                   refresh_owner = excluded.refresh_owner,
                   lease_until = excluded.lease_until
               WHERE (d1_cache.refresh_owner IS NULL OR d1_cache.lease_until <= ?)
                 AND (d1_cache.retry_after IS NULL OR d1_cache.retry_after <= ?)
                 AND d1_cache.expires_at <= ?
               RETURNING refresh_owner""",
            key, owner_token, now + lease_seconds, now, now, now,
        )
        return row is not None and row.get("refresh_owner") == owner_token

    async def store_success(self, key: str, owner_token: str, value: Any, *,
                            now: int, ttl_seconds: int) -> bool:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        row = await self._first(
            """UPDATE d1_cache
               SET payload = ?, expires_at = ?, refresh_owner = NULL, lease_until = NULL,
                   failures = 0, retry_after = NULL
               WHERE cache_key = ? AND refresh_owner = ? AND lease_until > ?
               RETURNING cache_key""",
            payload, now + ttl_seconds, key, owner_token, now,
        )
        return row is not None

    async def store_failure(self, key: str, owner_token: str, *, now: int) -> bool:
        row = await self._first(
            """UPDATE d1_cache
               SET failures = failures + 1,
                   retry_after = ? + MIN(?, ? * (1 << MIN(failures, 30))),
                   refresh_owner = NULL, lease_until = NULL
               WHERE cache_key = ? AND refresh_owner = ? AND lease_until > ?
               RETURNING failures""",
            now, self.max_backoff_seconds, self.base_backoff_seconds, key, owner_token, now,
        )
        return row is not None


def school_week_key(school_id: str, week_start: str) -> str:
    """Build a collision-safe canonical key for a school's timetable week."""
    if not school_id or not week_start:
        raise ValueError("school_id and week_start are required")
    return "timetable:" + json.dumps([school_id, week_start], ensure_ascii=False, separators=(",", ":"))
