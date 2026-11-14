import logging
import os
import threading
import time
from collections import deque

logger = logging.getLogger("opensigan.shutter")


def _env_int(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class Shutter:
    """Automatic load shutter for the API.

    Closes (trips) when the request rate inside a sliding window exceeds
    ``max_requests``, or when the 1-minute load average exceeds
    ``max_load``. While closed, every request is shed until the cooldown
    elapses; the shutter then reopens on its own. A limit of 0 disables
    that trip condition.
    """

    def __init__(
        self,
        max_requests=600,
        window_seconds=60,
        cooldown_seconds=30,
        max_load=8.0,
        time_fn=time.monotonic,
        load_fn=None,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.max_load = max_load
        self._time_fn = time_fn
        self._load_fn = load_fn if load_fn is not None else (lambda: os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0)
        self._lock = threading.Lock()
        self._hits = deque()
        self._closed_until = None

    @classmethod
    def from_environment(cls):
        return cls(
            max_requests=_env_int("SHUTTER_MAX_REQUESTS", 600),
            window_seconds=_env_int("SHUTTER_WINDOW_SECONDS", 60),
            cooldown_seconds=_env_int("SHUTTER_COOLDOWN_SECONDS", 30),
            max_load=_env_float("SHUTTER_MAX_LOAD", 8.0),
        )

    def check(self):
        """Record one request. Returns (allowed, retry_after_seconds)."""
        now = self._time_fn()
        with self._lock:
            if self._closed_until is not None:
                if now < self._closed_until:
                    return False, max(1, int(self._closed_until - now + 0.999))
                logger.info("shutter reopened after cooldown")
                self._closed_until = None
                self._hits.clear()

            cutoff = now - self.window_seconds
            while self._hits and self._hits[0] <= cutoff:
                self._hits.popleft()
            if self.max_requests > 0:
                self._hits.append(now)

            if self.max_requests > 0 and len(self._hits) > self.max_requests:
                return self._trip(now, f"request rate {len(self._hits)} in {self.window_seconds}s exceeded {self.max_requests}")
            if self.max_load > 0:
                try:
                    load = self._load_fn()
                except OSError:
                    load = 0.0
                if load > self.max_load:
                    return self._trip(now, f"load average {load:.2f} exceeded {self.max_load}")
            return True, 0

    def _trip(self, now, reason):
        self._closed_until = now + self.cooldown_seconds
        logger.warning("shutter closed for %ss: %s", self.cooldown_seconds, reason)
        return False, self.cooldown_seconds
