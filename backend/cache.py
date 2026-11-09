import json
import threading
import time
from collections import OrderedDict


class Cache:
    """Bounded, process-local cache with single-flight refreshes."""

    def __init__(self, ttl=1800, retry_delay=60, max_entries=256,
                 max_bytes=16 * 1024 * 1024, lock_stripes=64):
        if ttl < 0 or retry_delay < 0 or max_entries < 1 or max_bytes < 1 or lock_stripes < 1:
            raise ValueError("cache limits must be non-negative and capacities positive")
        self.ttl = ttl
        self.retry_delay = retry_delay
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.bytes_used = 0
        self.entries = OrderedDict()
        self.guard = threading.Lock()
        self.locks = tuple(threading.Lock() for _ in range(lock_stripes))

    def get(self, key, fetch):
        lock = self.locks[hash(key) % len(self.locks)]
        with lock:
            now = time.monotonic()
            with self.guard:
                entry = self.entries.get(key)
                if entry is not None:
                    self.entries.move_to_end(key)
                    value, fetched_at, retry_after = entry
                    if value is not None and now - fetched_at < self.ttl:
                        return json.loads(value)
                    if retry_after > now:
                        if value is not None:
                            return self._stale(value)
                        raise RuntimeError("cached fetch failure is in backoff")

            try:
                value = fetch()
                try:
                    cached = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
                except (TypeError, ValueError) as exc:
                    raise RuntimeError("fetch returned a non-JSON value") from exc
            except ValueError:
                raise
            except Exception:
                now = time.monotonic()
                with self.guard:
                    current = self.entries.get(key)
                    previous = current[0] if current else None
                    self._store(key, previous, current[1] if current else 0,
                                now + self.retry_delay)
                if previous is not None:
                    return self._stale(previous)
                raise

            with self.guard:
                if len(cached) <= self.max_bytes:
                    self._store(key, cached, time.monotonic(), 0)
                elif key in self.entries:
                    old = self.entries.pop(key)
                    self.bytes_used -= len(old[0]) if old[0] is not None else 0
            return json.loads(cached)

    @staticmethod
    def _stale(value):
        result = json.loads(value)
        if isinstance(result, dict):
            result["stale"] = True
        return result

    def _store(self, key, value, fetched_at, retry_after):
        old = self.entries.get(key)
        if old and old[0] is not None:
            self.bytes_used -= len(old[0])
        self.entries[key] = (value, fetched_at, retry_after)
        self.bytes_used += len(value) if value is not None else 0
        self.entries.move_to_end(key)
        while len(self.entries) > self.max_entries or self.bytes_used > self.max_bytes:
            _, removed = self.entries.popitem(last=False)
            self.bytes_used -= len(removed[0]) if removed[0] is not None else 0
