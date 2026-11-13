import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

from backend.history import HistoryStore


def lesson(subject="Math", teacher="A", period=1):
    return {"grade": 1, "class": 2,
            "date": (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat(), "period": period,
            "subject": subject, "teacher": teacher}


class HistoryTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(os.environ["LOCALAPPDATA"]) / "Temp" if os.name == "nt" else None
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.store = HistoryStore(Path(self.temp.name) / "history.sqlite")

    def tearDown(self):
        self.temp.cleanup()

    def test_baseline_then_add_delete_subject_teacher_and_noop(self):
        week = datetime.now(timezone.utc).date().isoformat()
        self.store.observe("s", week, [lesson()], datetime.now(timezone.utc))
        self.assertEqual(self.store.list("s", week)["changes"], [])
        self.store.observe("s", week, [lesson("Science", "B"), lesson("Art", period=2)], datetime.now(timezone.utc) + timedelta(seconds=1))
        result = self.store.list("s", week)
        self.assertEqual([c["type"] for c in result["changes"]], ["added", "changed"])
        self.assertEqual(result["changes"][0]["after"]["subject"], "Art")
        self.store.observe("s", week, [], datetime.now(timezone.utc) + timedelta(seconds=2))
        changes = self.store.list("s", week)["changes"]
        self.assertEqual(changes[0]["type"], "deleted")
        count = len(changes)
        self.store.observe("s", week, [], datetime.now(timezone.utc) + timedelta(seconds=3))
        self.assertEqual(len(self.store.list("s", week)["changes"]), count)

    def test_empty_baseline_is_still_baseline(self):
        self.store.observe("s", "w", [], datetime.now(timezone.utc))
        self.store.observe("s", "w", [lesson()], datetime.now(timezone.utc) + timedelta(seconds=1))
        self.assertEqual(self.store.list("s", "w")["changes"][0]["type"], "added")

    def test_latest_started_request_wins_but_observed_time_is_reported(self):
        base = datetime.now(timezone.utc)
        self.store.observe("s", "w", [lesson("new")], base + timedelta(seconds=2), started_at=base + timedelta(seconds=1))
        self.store.observe("s", "w", [lesson("old")], base + timedelta(seconds=3), started_at=base)
        self.assertEqual(self.store.list("s", "w")["changes"], [])
        self.store.observe("s", "w", [lesson("final")], base + timedelta(seconds=4), started_at=base + timedelta(seconds=2))
        change = self.store.list("s", "w")["changes"][0]
        self.assertEqual(change["observedAt"], (base + timedelta(seconds=4)).isoformat())
        self.assertEqual(change["after"]["subject"], "final")

    def test_cursor_keyset_pages_descending_and_validates(self):
        base = datetime.now(timezone.utc)
        self.store.observe("s", "w", [lesson()], base)
        for n in range(1, 5):
            self.store.observe("s", "w", [lesson(str(n))], base + timedelta(seconds=n))
        page1 = self.store.list("s", "w", limit=2)
        page2 = self.store.list("s", "w", cursor=page1["nextCursor"], limit=2)
        self.assertEqual([c["after"]["subject"] for c in page1["changes"]], ["4", "3"])
        self.assertEqual([c["after"]["subject"] for c in page2["changes"]], ["2", "1"])
        self.assertIsNone(page2["nextCursor"])
        for bad in (0, -1, "0", "1e2", "01", 1.2, True, str(1 << 63)):
            with self.subTest(cursor=bad), self.assertRaises(ValueError):
                self.store.list("s", "w", cursor=bad)

    def test_duplicate_keys_and_retention(self):
        with self.assertRaises(ValueError):
            self.store.observe("s", "w", [lesson(), lesson()], datetime.now(timezone.utc))
        old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        self.store.observe("s", "w", [lesson()], old)
        self.store.observe("s", "w", [lesson("new")], datetime.now(timezone.utc).isoformat())
        self.assertEqual(self.store.list("s", "w")["changes"], [])

    def test_concurrent_observations_are_atomic(self):
        base = datetime.now(timezone.utc)
        self.store.observe("s", "w", [lesson()], base)
        def update(n):
            self.store.observe("s", "w", [lesson(str(n))], base + timedelta(seconds=10 + n),
                               started_at=base + timedelta(seconds=n))
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(update, range(1, 5)))
        changes = self.store.list("s", "w", limit=10)["changes"]
        self.assertEqual(changes[0]["after"]["subject"], "4")
        self.store.observe("s", "w", [lesson("verify")], base + timedelta(seconds=20),
                           started_at=base + timedelta(seconds=5))
        latest = self.store.list("s", "w")["changes"][0]
        self.assertEqual(latest["before"]["subject"], "4")
        chronological = list(reversed(self.store.list("s", "w", limit=10)["changes"]))
        for previous, current in zip(chronological, chronological[1:]):
            self.assertEqual(previous["after"], current["before"])


if __name__ == "__main__":
    unittest.main()
