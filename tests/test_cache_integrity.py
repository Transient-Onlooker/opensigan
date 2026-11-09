import unittest

from backend.cache import Cache


class CacheIntegrityTests(unittest.TestCase):
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
