import unittest
import threading
from concurrent.futures import ThreadPoolExecutor

from backend.cache import Cache


class CacheIntegrityTests(unittest.TestCase):
    def test_eviction_during_failed_refresh_returns_inflight_stale_value(self):
        cache = Cache(ttl=0, max_entries=1, lock_stripes=2)
        cache.get(0, lambda: {"value": "old", "stale": False})
        started = threading.Event()
        release = threading.Event()

        def fail_after_eviction():
            started.set()
            if not release.wait(2):
                raise TimeoutError("refresh was not released")
            raise RuntimeError("upstream unavailable")

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(cache.get, 0, fail_after_eviction)
            try:
                self.assertTrue(started.wait(2))
                cache.get(1, lambda: {"value": "other"})
                self.assertNotIn(0, cache.entries)
            finally:
                release.set()
            self.assertEqual(future.result(timeout=2), {"value": "old", "stale": True})

    def test_oversized_refresh_preserves_last_good_value(self):
        cache = Cache(ttl=0, retry_delay=60, max_bytes=80)
        cache.get("key", lambda: {"value": "old", "stale": False})
        result = cache.get("key", lambda: {"value": "x" * 100})
        self.assertEqual(result, {"value": "old", "stale": True})

        def fail_if_called():
            self.fail("backoff should prevent another request")

        self.assertEqual(cache.get("key", fail_if_called), result)

    def test_oversized_initial_value_is_returned_without_caching(self):
        cache = Cache(max_bytes=10)
        value = {"value": "x" * 100}
        self.assertEqual(cache.get("key", lambda: value), value)
        self.assertEqual(len(cache.entries), 0)


if __name__ == "__main__":
    unittest.main()
