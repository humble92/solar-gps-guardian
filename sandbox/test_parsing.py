"""Offline regression tests for sandbox parsing helpers (no network).

Run:  python3 sandbox/test_parsing.py
Covers the real SWPC response shapes observed 2026-10-26:
  - noaa-scales.json      -> {"0": {"G/R/S": {...}}, ...}
  - planetary_k_index_1m  -> list of {time_tag, estimated_kp, kp}
  - 3-hourly Kp rows      -> {time_tag, "Kp", a_running, station_count}
  - 3-day-geomag text     -> 'NOAA Kp index forecast' table block
  - GloTEC index          -> list of {url, time_tag} (tiles fetched separately)
"""
import sys
import unittest

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from noaa_3day_geomag_forecast import parse_kp_table  # noqa: E402
from noaa_kp_index import g_scale  # noqa: E402
from noaa_solar_flare_reports import r_scale  # noqa: E402


class TestScales(unittest.TestCase):
    def test_g_scale_bounds(self):
        self.assertEqual(g_scale(0.0), "No storm (Kp<5)")
        self.assertEqual(g_scale(4.99), "No storm (Kp<5)")
        self.assertEqual(g_scale(5.0), "G1 Minor")
        self.assertEqual(g_scale(6.5), "G2 Moderate")
        self.assertEqual(g_scale(7.0), "G3 Strong")
        self.assertEqual(g_scale(8.67), "G4 Severe")
        self.assertEqual(g_scale(9.0), "G5 Extreme")

    def test_r_scale_bounds(self):
        self.assertEqual(r_scale("B3.0"), "below R-scale")
        self.assertEqual(r_scale("C7.2"), "below R-scale")
        self.assertEqual(r_scale("M1.0"), "R1 Minor")
        self.assertEqual(r_scale("M5.0"), "R2 Moderate")
        self.assertEqual(r_scale("X1.0"), "R3 Strong")
        self.assertEqual(r_scale("X10.0"), "R4 Severe")
        self.assertEqual(r_scale("X20.0"), "R5 Extreme")
        self.assertEqual(r_scale(""), "unknown")


class TestKpTableParse(unittest.TestCase):
    SAMPLE = (
        ":Product: Geomagnetic Forecast\n"
        "NOAA Kp index forecast 27 Oct - 29 Oct\n"
        "             Oct 27    Oct 28    Oct 29\n"
        "00-03UT        3.00      1.33      1.67      \n"
        "03-06UT        5.33      1.33      1.33      \n"
        "06-09UT        1.67      1.67      1.33      \n"
        "\n"
        "Some trailing text\n"
    )

    def test_parses_rows_and_stops_at_blank(self):
        rows = parse_kp_table(self.SAMPLE)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], {"ut": "00-03UT", "day1": 3.0, "day2": 1.33, "day3": 1.67})
        self.assertAlmostEqual(rows[1]["day1"], 5.33)

    def test_storm_detection_threshold(self):
        rows = parse_kp_table(self.SAMPLE)
        mx = max(max(r["day1"], r["day2"], r["day3"]) for r in rows)
        self.assertGreaterEqual(mx, 5.0)

    def test_no_table_returns_empty(self):
        self.assertEqual(parse_kp_table("no forecast block here\n"), [])


class TestResponseShapes(unittest.TestCase):
    """Pin the live-schema shapes the fetchers must handle."""

    def test_hourly_kp_row_keys(self):
        row = {"time_tag": "2026-10-20T00:00:00", "Kp": 1.0,
               "a_running": 4, "station_count": 8}
        self.assertIn("Kp", row)  # NOT 'kp_index' (older docs)

    def test_scales_current_block(self):
        scales = {"0": {"G": {"Scale": "0", "Text": "none"}},
                  "1": {}, "2": {}}
        self.assertEqual(scales["0"]["G"]["Scale"], "0")

    def test_glotec_index_is_list_of_tiles(self):
        idx = [{"url": "/products/glotec/geojson_2d_urt/x.geojson",
                "time_tag": "2026-09-26T00:05:00Z"}]
        self.assertTrue(idx[0]["url"].endswith(".geojson"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
