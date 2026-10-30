import unittest
from unittest.mock import patch

from backend.providers import dst, forecast_3d, kp, stereo, tec
from backend.providers.donki import fetch as fetch_donki


class TestProviderNormalize(unittest.TestCase):
    def test_kp_real_shape(self):
        raw = {"kp3": [{"time_tag": "2026-10-20T00:00:00", "Kp": 2.0,
                        "a_running": 7, "station_count": 8}],
               "kp1m": [{"time_tag": "t", "estimated_kp": 0.67, "kp": "1M"}],
               "forecast": [{"time_tag": "t", "kp": 5.0, "observed": "predicted"}],
               "scales": {"0": {"G": {"Scale": "0"}, "R": {}, "S": {}}}}
        f = kp.normalize(raw)
        self.assertEqual(f["kp"], 2.0)
        self.assertEqual(f["forecast_max_kp"], 5.0)

    def test_forecast_table_parse(self):
        txt = ("NOAA Kp index forecast 27 Oct - 29 Oct\n"
               "00-03UT        3.00      1.33      1.67\n\n")
        rows = forecast_3d.parse_kp_table(txt)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["day1"], 3.0)

    def test_dst_parse(self):
        line = "DST2610*01RRX020 " + " ".join(str(i) for i in range(24)) + " 5"
        rows = dst.parse_dst(line)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["hourly"][0], 0)

    def test_stereo_spike_filtered(self):
        f = stereo.normalize({"rows": [{"timestamp": "t", "Bt_nT": 834.0,
                                        "speed_KPS": 400, "density_cm3": 5}]})
        self.assertTrue(f["spike_filtered"])
        self.assertIsNone(f["speed_km_s"])

    def test_donki_calls_ccmc_without_api_key(self):
        seen = {}

        def fake(url, params=None, timeout=30):
            seen["url"] = url
            seen["params"] = params
            return [{"flrID": "2026-FLR"}]

        with patch("backend.providers.donki.http_get_json", side_effect=fake):
            raw = fetch_donki(env={"NASA_API_KEY": "k"})
        self.assertTrue(seen["url"].startswith("https://ccmc.gsfc.nasa.gov/DONKI-API/get/"))
        self.assertNotIn("api_key", seen["params"])
        self.assertEqual(raw["data"]["CME"][0]["flrID"], "2026-FLR")
        self.assertEqual(raw["key_tier"], "retained")
        self.assertEqual(raw["errors"], {})

    def test_tec_empty_index_tolerated(self):
        f = tec.normalize({"index": [], "tile": None})
        self.assertFalse(f["available"])


if __name__ == "__main__":
    unittest.main()
