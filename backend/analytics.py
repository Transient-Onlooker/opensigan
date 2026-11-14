"""Privacy-minimizing first-party usage analytics."""

import hashlib
import hmac
import sqlite3
import threading
import uuid
import logging
from queue import Full, Queue
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    SEOUL = ZoneInfo("Asia/Seoul")
except ZoneInfoNotFoundError:
    SEOUL = timezone(timedelta(hours=9), name="Asia/Seoul")


class AnalyticsStore:
    def __init__(self, path, secret):
        if len(secret) < 32:
            raise ValueError("analytics secret must contain at least 32 characters")
        self.path = str(path)
        self.secret = secret.encode("utf-8")
        self._memory_uri = None
        self._memory_anchor = None
        self._purge_lock = threading.Lock()
        self._last_purge_day = None
        if self.path == ":memory:":
            self._memory_uri = f"file:opensigan-analytics-{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._memory_anchor = sqlite3.connect(self._memory_uri, uri=True)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            if self.path != ":memory:":
                db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS page_views (
                    id INTEGER PRIMARY KEY, day TEXT NOT NULL,
                    visitor_hash TEXT NOT NULL, session_hash TEXT NOT NULL,
                    page TEXT NOT NULL, occurred_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_requests (
                    id INTEGER PRIMARY KEY, day TEXT NOT NULL, route TEXT NOT NULL,
                    method TEXT NOT NULL, status INTEGER NOT NULL,
                    duration_ms REAL NOT NULL, occurred_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS page_views_day ON page_views(day);
                CREATE INDEX IF NOT EXISTS api_requests_day ON api_requests(day);
            """)
            self._purge_if_due(db, self._now()[0])
            db.commit()

    def _connect(self):
        db = sqlite3.connect(self._memory_uri, uri=True, timeout=0.05) if self._memory_uri else sqlite3.connect(self.path, timeout=0.05)
        db.row_factory = sqlite3.Row
        return db

    def close(self):
        if self._memory_anchor is not None:
            self._memory_anchor.close()
            self._memory_anchor = None

    def _hash(self, value):
        return hmac.new(self.secret, value.encode("utf-8"), hashlib.sha256).hexdigest()

    @staticmethod
    def _now():
        now = datetime.now(SEOUL)
        return now.date().isoformat(), now.isoformat()

    @staticmethod
    def _valid_uuid4(value):
        try:
            parsed = uuid.UUID(value)
        except (AttributeError, TypeError, ValueError):
            return False
        return parsed.version == 4 and str(parsed) == value

    def record_pageview(self, visitor_id, session_id, page):
        if not self._valid_uuid4(visitor_id):
            raise ValueError("visitor id is invalid")
        if not self._valid_uuid4(session_id):
            raise ValueError("session id is invalid")
        if page not in ("/", "/timetable", "/meals"):
            raise ValueError("page is invalid")
        day, occurred_at = self._now()
        with closing(self._connect()) as db:
            self._purge_if_due(db, day)
            db.execute("INSERT INTO page_views(day, visitor_hash, session_hash, page, occurred_at) VALUES (?, ?, ?, ?, ?)",
                       (day, self._hash(visitor_id), self._hash(session_id), page, occurred_at))
            db.commit()

    def record_api(self, route, method, status, duration_ms):
        day, occurred_at = self._now()
        with closing(self._connect()) as db:
            self._purge_if_due(db, day)
            db.execute("INSERT INTO api_requests(day, route, method, status, duration_ms, occurred_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (day, route, method, status, max(0, duration_ms), occurred_at))
            db.commit()

    def _purge_if_due(self, db, today):
        with self._purge_lock:
            if self._last_purge_day == today:
                return
            cutoff = (datetime.fromisoformat(today).date() - timedelta(days=89)).isoformat()
            db.execute("DELETE FROM page_views WHERE day < ?", (cutoff,))
            db.execute("DELETE FROM api_requests WHERE day < ?", (cutoff,))
            db.commit()
            self._last_purge_day = today

    def summary(self, days=30):
        if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 90:
            raise ValueError("days must be between 1 and 90")
        today = self._now()[0]
        start = (datetime.fromisoformat(today).date() - timedelta(days=days - 1)).isoformat()
        with closing(self._connect()) as db:
            self._purge_if_due(db, today)
            db.commit()
            visitors = db.execute("SELECT COUNT(DISTINCT visitor_hash) FROM page_views WHERE day >= ?", (start,)).fetchone()[0]
            sessions = db.execute("SELECT COUNT(DISTINCT session_hash) FROM page_views WHERE day >= ?", (start,)).fetchone()[0]
            views = db.execute("SELECT COUNT(*) FROM page_views WHERE day >= ?", (start,)).fetchone()[0]
            api = db.execute("SELECT COUNT(*), SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END), AVG(duration_ms) FROM api_requests WHERE day >= ?", (start,)).fetchone()
            daily = db.execute("""SELECT d.day,
                (SELECT COUNT(DISTINCT visitor_hash) FROM page_views p WHERE p.day=d.day) visitors,
                (SELECT COUNT(DISTINCT session_hash) FROM page_views p WHERE p.day=d.day) sessions,
                (SELECT COUNT(*) FROM page_views p WHERE p.day=d.day) page_views,
                (SELECT COUNT(*) FROM api_requests a WHERE a.day=d.day) api_requests
                FROM (SELECT day FROM page_views WHERE day >= ? UNION SELECT day FROM api_requests WHERE day >= ?) d
                ORDER BY d.day""", (start, start)).fetchall()
            routes = db.execute("SELECT route, COUNT(*) requests, SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) errors, ROUND(AVG(duration_ms), 2) avg_ms FROM api_requests WHERE day >= ? GROUP BY route ORDER BY requests DESC", (start,)).fetchall()
        count = api[0] or 0
        errors = api[1] or 0
        return {
            "periodDays": days,
            "visitors": visitors,
            "sessions": sessions,
            "pageViews": views,
            "apiRequests": count,
            "apiErrors": errors,
            "apiErrorRate": round(errors / count, 4) if count else 0,
            "apiAverageMs": round(api[2], 2) if api[2] is not None else 0,
            "daily": [dict(row) for row in daily],
            "routes": [dict(row) for row in routes],
        }


class ApiRecorder:
    """Bound telemetry work so disk contention cannot hold up timetable responses."""

    def __init__(self, store_factory, capacity=1024):
        self.queue = Queue(maxsize=capacity)
        self.store_factory = store_factory
        self.dropped = 0
        self._start_lock = threading.Lock()
        self._worker = None

    def submit(self, *event):
        with self._start_lock:
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="analytics-writer", daemon=True)
                self._worker.start()
        try:
            self.queue.put_nowait(event)
        except Full:
            self.dropped += 1

    def _run(self):
        while True:
            event = self.queue.get()
            try:
                store = self.store_factory()
                if store is not None:
                    store.record_api(*event)
            except Exception:
                self.dropped += 1
                logging.getLogger("opensigan").warning("analytics event could not be stored")
            finally:
                self.queue.task_done()
