import tempfile
import pathlib
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

    def test_storm_skips_moderate_and_sends_critical(self):
        self.store.subscribe("a@b.c", "High latitude", 80.6, -72.6)
        moderate = {**QUIET, "now": {"kp": 5.0, "g_scale": {"Scale": "1"}},
                    "forecast_3d": {"max_kp": 5.0}}
        critical = {**QUIET, "now": {"kp": 8.0, "g_scale": {"Scale": "3"}},
                    "forecast_3d": {"max_kp": 8.0}}
        r1 = mailer.run_batch(self.store, moderate, kind="storm", dry_dir=f"{self.tmp}/out")
        r2 = mailer.run_batch(self.store, critical, kind="storm", dry_dir=f"{self.tmp}/out")
        self.assertEqual(r1["sent"], 0)
        self.assertEqual(r2["sent"], 1)
        sent = list(pathlib.Path(f"{self.tmp}/out").glob("*.eml"))
        self.assertEqual(len(sent), 1)
        text = sent[0].read_text()
        self.assertIn("Subject: Solar wind Critical Alarm", text)
        self.assertIn("Scored for 80.60, -72.60", text)

    def test_storm_mail_uses_subscriber_coordinates(self):
        self.store.subscribe("high@b.c", "Aurora", 80.6, -72.6)
        self.store.subscribe("eq@b.c", "Equator", 0.0, 0.0)
        snap = {**QUIET, "fetched_at": "2026-10-30T12:00:00Z",
                "now": {"kp": 8.0}, "forecast_3d": {"max_kp": 8.0}}
        r = mailer.run_batch(self.store, snap, kind="storm", dry_dir=f"{self.tmp}/out")
        self.assertEqual(r["sent"], 1)
        bodies = [p.read_text() for p in pathlib.Path(f"{self.tmp}/out").glob("*.eml")]
        self.assertEqual(len(bodies), 1)
        self.assertIn("Scored for 80.60, -72.60", bodies[0])
        self.assertNotIn("Scored for 0.00, 0.00", bodies[0])

    def test_daily_mail_scores_each_subscriber(self):
        self.store.subscribe("day@b.c", "Dayside equator", 0.0, 0.0)
        self.store.subscribe("night@b.c", "Night side", 45.0, 180.0)
        snap = {**QUIET, "fetched_at": "2026-10-30T12:00:00Z",
                "now": {"kp": 2.0}, "forecast_3d": {"max_kp": 2.0},
                "events": {"worst_flare_7d": "X1.0", "cme_earth_arrivals": []}}
        r = mailer.run_batch(self.store, snap, kind="daily", dry_dir=f"{self.tmp}/out")
        self.assertEqual(r["sent"], 2)
        texts = [p.read_text() for p in pathlib.Path(f"{self.tmp}/out").glob("*.eml")]
        day = next(t for t in texts if "Scored for 0.00, 0.00" in t)
        night = next(t for t in texts if "Scored for 45.00, 180.00" in t)
        self.assertIn("GPS risk: LOW (37/100)", day)
        self.assertIn("GPS risk: LOW (16/100)", night)
        self.assertIn("flare bonus omitted", night)

    def test_tec_grid_roundtrip_and_snapshot_pointer(self):
        snap = build_snapshot(
            {"kp": {"ok": True, "kp": 1.0}, "donki": {"ok": True},
             "tec": {"ok": True, "available": True, "tec_max": 55,
                     "latest_time": "t", "grid": [[-79.4, 43.7, 55.0]]}}, {})
        self.assertEqual(snap["tec"]["grid_ref"], "tec_grid:1")
        self.assertNotIn("grid", snap["tec"])
        self.assertNotIn("grid", snap["fragments"]["tec"])
        from backend import pipeline
        pipeline.persist(self.store, snap)
        self.assertNotIn("_tec_grid", self.store.load_snapshot())
        self.assertEqual(self.store.load_tec_grid(), [[-79.4, 43.7, 55.0]])
        pipeline.persist(self.store, {"fetched_at": "x", "_tec_grid": []})
        self.assertEqual(self.store.load_tec_grid(), [[-79.4, 43.7, 55.0]])


if __name__ == "__main__":
    unittest.main()
