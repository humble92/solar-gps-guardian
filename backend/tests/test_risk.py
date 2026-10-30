import unittest

from backend.risk import assess, route_segments, score_for


class TestScore(unittest.TestCase):
    def test_kp7_is_critical(self):
        self.assertEqual(score_for(kp=7.0)["level"], "CRITICAL")

    def test_quiet_is_low(self):
        r = score_for(kp=1.0, worst_flare="B3.0")
        self.assertEqual(r["level"], "LOW")

    def test_flare_and_cme_bonuses(self):
        r = score_for(kp=2.0, worst_flare="X1.0", cme_arrivals=[{"arrival": "x"}])
        self.assertEqual(r["score"], 2 * 10 + 25 + 20)

    def test_tec_bonus_and_clamp(self):
        r = score_for(kp=9.0, worst_flare="X9.9", tec_local=80)
        self.assertEqual(r["score"], 100)

    def test_missing_inputs_safe(self):
        r = score_for()
        self.assertEqual((r["score"], r["level"]), (0, "LOW"))

    def test_assess_uses_forecast_max(self):
        snap = {"now": {"kp": 1.0}, "forecast_3d": {"max_kp": 7.0},
                "events": {}, "degraded": False}
        self.assertEqual(assess(snap)["level"], "CRITICAL")

    def test_route_segments(self):
        snap = {"now": {"kp": 1.0}, "forecast_3d": {"max_kp": 1.0}, "events": {}}
        segs = route_segments(snap, [{"label": "a", "lat": 1, "lon": 2, "tec": 80},
                                     {"label": "b", "lat": 3, "lon": 4, "tec": 1}])
        self.assertEqual([s["label"] for s in segs], ["a", "b"])
        self.assertGreater(segs[0]["score"], segs[1]["score"])


if __name__ == "__main__":
    unittest.main()
