import json
import unittest

from backend.app import dispatch_request
from backend.shutter import Shutter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_shutter(clock, **kwargs):
    kwargs.setdefault("time_fn", clock)
    kwargs.setdefault("load_fn", lambda: 0.0)
    return Shutter(**kwargs)


class ShutterTest(unittest.TestCase):
    def test_allows_requests_under_limit(self):
        clock = FakeClock()
        shutter = make_shutter(clock, max_requests=3, window_seconds=60, cooldown_seconds=30)
        for _ in range(3):
            allowed, _ = shutter.check()
            self.assertTrue(allowed)

    def test_trips_when_rate_exceeds_limit(self):
        clock = FakeClock()
        shutter = make_shutter(clock, max_requests=3, window_seconds=60, cooldown_seconds=30)
        for _ in range(3):
            shutter.check()
        allowed, retry_after = shutter.check()
        self.assertFalse(allowed)
        self.assertEqual(retry_after, 30)

    def test_stays_closed_during_cooldown_and_reopens(self):
        clock = FakeClock()
        shutter = make_shutter(clock, max_requests=1, window_seconds=60, cooldown_seconds=30)
        shutter.check()
        self.assertFalse(shutter.check()[0])
        clock.advance(29)
        self.assertFalse(shutter.check()[0])
        clock.advance(1)
        self.assertTrue(shutter.check()[0])

    def test_window_slides(self):
        clock = FakeClock()
        shutter = make_shutter(clock, max_requests=2, window_seconds=10, cooldown_seconds=30)
        shutter.check()
        shutter.check()
        clock.advance(11)
        self.assertTrue(shutter.check()[0])

    def test_trips_on_high_load(self):
        clock = FakeClock()
        shutter = make_shutter(clock, max_requests=0, max_load=4.0, load_fn=lambda: 9.5)
        allowed, _ = shutter.check()
        self.assertFalse(allowed)

    def test_limits_disabled_with_zero(self):
        clock = FakeClock()
        shutter = make_shutter(clock, max_requests=0, max_load=0)
        for _ in range(100):
            self.assertTrue(shutter.check()[0])


class DispatchShutterTest(unittest.TestCase):
    def test_dispatch_sheds_with_503_and_status_stays_up(self):
        clock = FakeClock()
        shutter = make_shutter(clock, max_requests=1, window_seconds=60, cooldown_seconds=30)

        status, _, _ = dispatch_request("GET", "/api/v1/unknown", "", shutter_instance=shutter)
        self.assertEqual(status, 404)

        status, headers, body = dispatch_request("GET", "/api/v1/unknown", "", shutter_instance=shutter)
        self.assertEqual(status, 503)
        self.assertEqual(headers["Retry-After"], "30")
        self.assertIn("error", json.loads(body.decode("utf-8")))

        status, _, body = dispatch_request("GET", "/api/v1/status", "", shutter_instance=shutter)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body.decode("utf-8")), {"status": "ok", "scope": "process liveness"})


if __name__ == "__main__":
    unittest.main()
