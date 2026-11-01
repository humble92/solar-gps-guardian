import unittest

from backend.local_score import score_point, score_route
from backend.risk import (assess, high_band_start, latitude_band, route_segments,
                          score_for, xray_class)

NOON = {"fetched_at": "2026-10-30T12:00:00Z", "degraded": False,
        "now": {"kp": 2.0}, "forecast_3d": {"max_kp": 2.0},
        "events": {"xray_flux": 1.0e-4, "cme_earth_arrivals": []}}  # X1.0 in progress


def fresh_grid(cells, time_tag="2026-10-30T10:30:00Z"):  # 1.5 h before NOON
    return {"time_tag": time_tag, "cells": cells}


class TestScore(unittest.TestCase):
    def test_kp7_is_critical(self):
        self.assertEqual(score_for(kp=7.0)["level"], "CRITICAL")

    def test_quiet_is_low(self):
        r = score_for(kp=1.0, xray_flux=3.0e-7)
        self.assertEqual(r["level"], "LOW")

    def test_flare_and_cme_bonuses(self):
        r = score_for(kp=2.0, xray_flux=1.0e-4, cme_arrivals=[{"arrival": "x"}])  # unreadable: counts
        self.assertEqual(r["score"], 2 * 10 + 25 + 20)

    def test_tec_bonus_and_clamp(self):
        r = score_for(kp=9.0, xray_flux=9.9e-4, tec_local=80)
        self.assertEqual(r["score"], 100)

    def test_flare_term_follows_current_xray_class(self):
        self.assertEqual(xray_class(2.2e-7), "B2.2")
        self.assertEqual(xray_class(3.4e-5), "M3.4")
        self.assertIsNone(xray_class(None))
        self.assertEqual(score_for(xray_flux=9.9e-6)["score"], 0)   # C9.9
        self.assertEqual(score_for(xray_flux=1.0e-5)["score"], 15)  # M1.0
        self.assertEqual(score_for(xray_flux=1.0e-4)["score"], 25)  # X1.0

    def test_last_weeks_flare_is_not_scored(self):
        snap = {**NOON, "events": {"worst_flare_7d": "X5.0", "xray_flux": 2.0e-7}}
        r = assess(snap, lat=0.0, lon=0.0)
        self.assertEqual(r["score"], 12)  # Kp 2 x 10 x 0.6, no flare bonus
        self.assertIn("X5.0 (not scored)", r["advisory"])

    def test_cme_counts_only_near_its_arrival(self):
        now = "2026-10-30T12:00:00Z"
        cme = lambda when: [{"arrival": when}]
        self.assertEqual(score_for(cme_arrivals=cme("2026-11-01T12:00Z"), now_iso=now)["score"], 20)  # +48 h
        self.assertEqual(score_for(cme_arrivals=cme("2026-10-29T18:00Z"), now_iso=now)["score"], 20)  # -18 h
        self.assertEqual(score_for(cme_arrivals=cme("2026-10-25T06:00Z"), now_iso=now)["score"], 0)   # days ago
        self.assertEqual(score_for(cme_arrivals=cme("2026-11-04T12:00Z"), now_iso=now)["score"], 0)   # +5 days
        self.assertEqual(score_for(cme_arrivals=cme("+18h"), now_iso=now)["score"], 20)  # unreadable counts

    def test_degraded_sentence_names_the_missing_feed(self):
        snap = {**NOON, "degraded": True,
                "flags": {"donki_available": True, "tec_available": False}}
        self.assertIn("DEGRADED MODE: GloTEC missing in this snapshot; scored with the feeds "
                      "that answered.", assess(snap)["advisory"])

    def test_gfz_kp_cross_check_takes_the_larger(self):
        base = {**NOON, "events": {}, "now": {"kp": 3.67}, "forecast_3d": {"max_kp": 3.0}}
        close = assess({**base, "kp_gfz": {"ok": True, "kp": 3.0}})
        self.assertEqual(close["inputs"]["kp_scored"], 3.67)
        self.assertNotIn("Kp sources differ", close["advisory"])
        higher = assess({**base, "kp_gfz": {"ok": True, "kp": 5.0}})
        self.assertEqual(higher["inputs"]["kp_scored"], 5.0)
        self.assertEqual(higher["score"], 50)
        self.assertIn("Kp sources differ (GFZ 5.0, SWPC 3.67); the larger is scored.", higher["advisory"])
        failed = assess({**base, "kp_gfz": {"ok": False, "error": "x"}})
        self.assertIsNone(failed["inputs"]["kp_gfz"])
        self.assertEqual(failed["inputs"]["kp_scored"], 3.67)

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

    def test_high_band_widens_with_kp(self):
        iowa = (41.59, -93.62)  # geomagnetic latitude ~50.3
        self.assertEqual(high_band_start(None), 55.0)
        self.assertEqual(high_band_start(3.0), 55.0)
        self.assertAlmostEqual(high_band_start(9.0), 49.8)
        self.assertEqual(latitude_band(*iowa, kp=3.0)[0], "mid")
        self.assertEqual(latitude_band(*iowa, kp=9.0)[0], "high")
        quiet = {**NOON, "now": {"kp": 3.0}, "forecast_3d": {"max_kp": 3.0}, "events": {}}
        storm = {**NOON, "now": {"kp": 9.0}, "forecast_3d": {"max_kp": 9.0}, "events": {}}
        self.assertEqual(assess(quiet, lat=iowa[0], lon=iowa[1])["inputs"]["kp_factor"], 0.8)
        self.assertEqual(assess(storm, lat=iowa[0], lon=iowa[1])["inputs"]["kp_factor"], 1.0)

    def test_ovation_oval_gives_full_kp_weight(self):
        iowa = (41.59, -93.62)  # mid band at Kp 3 by latitude alone
        quiet = {**NOON, "now": {"kp": 3.0}, "forecast_3d": {"max_kp": 3.0}, "events": {}}
        self.assertEqual(assess(quiet, lat=iowa[0], lon=iowa[1], aurora=9)["inputs"]["kp_factor"], 0.8)
        under = assess(quiet, lat=iowa[0], lon=iowa[1], aurora=10)
        self.assertEqual(under["inputs"]["kp_factor"], 1.0)
        self.assertIn("Under the auroral oval now", under["advisory"])

    def test_tec_anomaly_term(self):
        self.assertEqual(score_for(tec_anomaly=9.9)["score"], 0)
        self.assertEqual(score_for(tec_anomaly=10.0)["score"], 10)
        self.assertEqual(score_for(tec_anomaly=-12.0)["score"], 10)  # depletion counts too
        self.assertEqual(score_for(tec_local=60, tec_anomaly=15)["score"], 20)
        r = assess(NOON, lat=0.0, lon=0.0, tec_anomaly=12.0)
        self.assertIn("+12 TECU from its 30-day median", r["advisory"])

    def test_score_point_reads_both_grids(self):
        snap = {**NOON, "now": {"kp": 3.0}, "forecast_3d": {"max_kp": 3.0}, "events": {}}
        grid = fresh_grid([[-93.6, 41.6, 20.0, 11.0]])
        aurora = [[266, 42, 15]]  # -93.62 E -> 266
        r = score_point(snap, 41.59, -93.62, grid=grid, aurora=aurora)
        self.assertEqual(r["inputs"]["tec_anomaly"], 11.0)
        self.assertEqual(r["inputs"]["aurora_local"], 15)
        self.assertEqual(r["score"], 3 * 10 * 1.0 + 10)

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
        with_tec = score_point(NOON, 0.0, 0.0, grid=fresh_grid([[0.0, 0.0, 80.0]]))
        self.assertIsNone(bare["inputs"]["tec_local"])
        self.assertEqual(with_tec["inputs"]["tec_local"], 80.0)
        self.assertEqual(with_tec["score"], bare["score"] + 10)

    def test_tec_older_than_limit_is_skipped_and_age_is_shown(self):
        cells = [[0.0, 0.0, 80.0, 12.0]]
        fresh = score_point(NOON, 0.0, 0.0, grid=fresh_grid(cells))
        self.assertEqual(fresh["inputs"]["tec_age_h"], 1.5)
        self.assertIn("Local TEC 80 TECU (GloTEC 10:30 UTC, 1.5 h old)", fresh["advisory"])
        stale = score_point(NOON, 0.0, 0.0, grid=fresh_grid(cells, "2026-10-30T08:30:00Z"))
        self.assertIsNone(stale["inputs"]["tec_local"])
        self.assertIsNone(stale["inputs"]["tec_anomaly"])
        self.assertEqual(fresh["score"] - stale["score"], 20)  # both TEC terms
        self.assertIn("TEC terms skipped: grid older than 3 h (GloTEC 08:30 UTC, 3.5 h old)",
                      stale["advisory"])
        untimed = score_point(NOON, 0.0, 0.0, grid=cells)  # stored before tile times
        self.assertIsNone(untimed["inputs"]["tec_local"])

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
        live_gfz = {**quiet, "kp_gfz": {"ok": True, "kp": 3.0}}
        hypo = score_route(live_gfz, points, scenario="storm")["worst"]["advisory"]
        self.assertNotIn("Kp sources differ", hypo)


if __name__ == "__main__":
    unittest.main()
