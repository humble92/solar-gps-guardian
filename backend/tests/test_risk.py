import unittest

from backend.local_score import score_point, score_route
from backend.risk import assess, latitude_band, route_segments, score_for

NOON = {"fetched_at": "2026-10-30T12:00:00Z", "degraded": False,
        "now": {"kp": 2.0}, "forecast_3d": {"max_kp": 2.0},
        "events": {"worst_flare_7d": "X1.0", "cme_earth_arrivals": []}}


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

    def test_latitude_band_scales_only_the_kp_term(self):
        self.assertEqual(latitude_band(80.6, -72.6)[0], "high")
        self.assertEqual(latitude_band(40.0, -72.6)[0], "mid")
        self.assertEqual(latitude_band(0.0, 0.0)[0], "low")
        high = assess(NOON, lat=80.6, lon=-72.6)
        low = assess(NOON, lat=0.0, lon=0.0)
        self.assertEqual(high["inputs"]["kp_factor"], 1.0)
        self.assertEqual(low["inputs"]["kp_factor"], 0.6)
        self.assertGreater(high["score"], low["score"])
        self.assertIn("Planetary Kp", high["advisory"])

    def test_night_side_omits_flare_bonus(self):
        day = assess(NOON, lat=0.0, lon=0.0)
        night = assess(NOON, lat=0.0, lon=180.0)
        self.assertTrue(day["inputs"]["dayside"])
        self.assertFalse(night["inputs"]["dayside"])
        self.assertEqual(day["score"] - night["score"], 25)
        self.assertIn("flare bonus omitted", night["advisory"])

    def test_same_snapshot_differs_by_place_and_local_time(self):
        day_eq = assess(NOON, lat=0.0, lon=0.0, tec_local=80)
        night_mid = assess(NOON, lat=45.0, lon=180.0, tec_local=10)
        self.assertEqual(latitude_band(45.0, 180.0)[0], "mid")
        self.assertNotEqual(day_eq["score"], night_mid["score"])
        self.assertTrue(day_eq["inputs"]["dayside"])
        self.assertFalse(night_mid["inputs"]["dayside"])

    def test_missing_tec_grid_drops_only_the_tec_bonus(self):
        bare = score_point(NOON, 0.0, 0.0, grid=[])
        with_tec = score_point(NOON, 0.0, 0.0, grid=[[0.0, 0.0, 80.0]])
        self.assertIsNone(bare["inputs"]["tec_local"])
        self.assertEqual(with_tec["inputs"]["tec_local"], 80.0)
        self.assertEqual(with_tec["score"], bare["score"] + 10)

    def test_route_samples_use_each_points_local_time(self):
        scored = score_route(NOON, [
            {"label": "day", "lat": 0.0, "lon": 0.0},
            {"label": "night", "lat": 0.0, "lon": 180.0},
        ])
        self.assertEqual([s["label"] for s in scored["segments"]], ["day", "night"])
        self.assertGreater(scored["segments"][0]["score"], scored["segments"][1]["score"])
        self.assertEqual(scored["worst"]["label"], "day")

    def test_storm_scenario_is_a_dangerous_hypothetical(self):
        quiet = {"fetched_at": "2026-10-30T12:00:00Z", "degraded": False,
                 "now": {"kp": 1.0}, "forecast_3d": {"max_kp": 1.0}, "events": {}}
        points = [{"label": "toronto", "lat": 43.65, "lon": -79.38}]
        live = score_route(quiet, points)
        storm = score_route(quiet, points, scenario="storm")
        self.assertEqual(live["scenario"], "live")
        self.assertEqual(storm["scenario"], "storm")
        self.assertEqual(storm["worst"]["level"], "CRITICAL")
        self.assertEqual(storm["worst"]["score"], 100)
        self.assertGreater(storm["worst"]["score"], live["worst"]["score"])


if __name__ == "__main__":
    unittest.main()
