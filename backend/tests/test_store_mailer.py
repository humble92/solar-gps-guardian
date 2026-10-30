import tempfile
import unittest

from backend import mailer
from backend.pipeline import build_snapshot
from backend.store import Store

QUIET = {"snapshot_version": 1, "fetched_at": "2026-10-27T00:00:00Z",
         "degraded": False, "now": {"kp": 1.0, "g_scale": {"Scale": "0"}},
         "forecast_3d": {"max_kp": 1.0}, "events": {"cme_earth_arrivals": []}}


class TestSnapshotDegraded(unittest.TestCase):
    def test_degraded_flags(self):
        snap = build_snapshot(
            {"kp": {"ok": True, "kp": 1.0}, "donki": {"ok": False},
             "tec": {"ok": False, "available": False}}, {})
        self.assertTrue(snap["degraded"])
        self.assertFalse(snap["flags"]["donki_available"])


class TestStoreMailer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = Store(f"{self.tmp}/t.db")

    def test_subscribe_unsubscribe(self):
        self.store.subscribe("a@b.c", "Toronto", 43.7, -79.4)
        self.assertEqual(len(self.store.list_active()), 1)
        self.assertTrue(self.store.unsubscribe("a@b.c"))
        self.assertEqual(len(self.store.list_active()), 0)

    def test_batch_dedup_and_token(self):
        self.store.subscribe("a@b.c", "Toronto", 43.7, -79.4)
        r1 = mailer.run_batch(self.store, QUIET, kind="daily", dry_dir=f"{self.tmp}/out")
        r2 = mailer.run_batch(self.store, QUIET, kind="daily", dry_dir=f"{self.tmp}/out")
        self.assertEqual((r1["sent"], r2["sent"]), (1, 0))
        tok = mailer.sign("a@b.c")
        self.assertTrue(mailer.verify("a@b.c", tok))
        self.assertFalse(mailer.verify("a@b.c", "bad"))

    def test_storm_not_triggered_when_quiet(self):
        self.store.subscribe("a@b.c", "Toronto", 43.7, -79.4)
        r = mailer.run_batch(self.store, QUIET, kind="storm", dry_dir=f"{self.tmp}/out")
        self.assertEqual(r["sent"], 0)


if __name__ == "__main__":
    unittest.main()
