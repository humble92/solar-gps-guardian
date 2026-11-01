import unittest
from unittest.mock import patch

from backend.providers import dst, forecast_3d, kp, ovation, stereo, tec
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

    def test_dst_month_start_falls_back_to_last_month(self):
        import datetime as dt
        from backend.providers.base import ProviderError
        day = lambda tag, vals: f"DST{tag}*01RRX020 " + " ".join(str(v) for v in vals) + " 5"
        october = day("2610", [-5] * 24) + "\n" + day("2610", [-12] * 20 + [9999] * 4)
        empty_nov = day("2611", [9999] * 24)
        now = dt.datetime(2026, 11, 1, 0, 5, tzinfo=dt.timezone.utc)

        def fake(pages):
            def get(url, *a, **k):
                if url not in pages:
                    raise ProviderError(f"GET {url}: HTTP Error 404")
                return pages[url]
            return get
        oct_url, nov_url = dst._month_url(dt.date(2026, 10, 31)), dst._month_url(now)
        with patch.object(dst, "http_get_text", fake({oct_url: october})):
            self.assertEqual(dst.fetch(now=now)["text"], october)  # November 404
        with patch.object(dst, "http_get_text", fake({oct_url: october, nov_url: empty_nov})):
            self.assertEqual(dst.fetch(now=now)["text"], october)  # November all 9999
        f = dst.normalize({"text": october + "\n" + empty_nov})
        self.assertEqual((f["latest_hour_dst"], f["min_dst"]), (-12, -12))

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

    def test_xray_gap_falls_back_to_secondary(self):
        from backend.providers import flares
        row = lambda sat, flux: {"time_tag": "t", "satellite": sat, "flux": flux, "energy": "0.1-0.8nm"}
        short = {"time_tag": "t", "satellite": 18, "flux": 1e-9, "energy": "0.05-0.4nm"}
        ok = flares.normalize({"flux": [row(18, 3e-7), short]})
        self.assertEqual((ok["xray_long"], ok["xray_satellite"]), (3e-7, 18))
        gap = flares.normalize({"flux": [row(18, 0.0)], "flux_secondary": [row(19, 2.3e-7)]})
        self.assertEqual((gap["xray_long"], gap["xray_satellite"]), (2.3e-7, 19))
        both = flares.normalize({"flux": [row(18, 0.0)], "flux_secondary": []})
        self.assertIsNone(both["xray_long"])

    def test_tec_listing_fallback_picks_newest_tile(self):
        html = ('<a href="glotec_icao_20261031T193500Z.geojson">x</a>'
                '<a href="glotec_icao_20261031T213500Z.geojson">x</a>'
                '<a href="glotec_icao_20260930T213500Z.geojson">x</a>')
        idx = tec._index_from_listing(html)
        self.assertEqual(idx[-1], {"time_tag": "2026-10-31T21:35:00Z",
                                   "url": "/products/glotec/geojson_2d_urt/glotec_icao_20261031T213500Z.geojson"})
        self.assertEqual(tec._index_from_listing(""), [])

    def test_donki_earth_arrival_from_enlil_shock_time(self):
        from backend.providers import donki
        sims = [  # shape of WSAEnlilSimulations, 2026-10
            {"estimatedShockArrivalTime": "2026-10-25T06:00Z", "isEarthGB": False,
             "isEarthMinorImpact": True, "kp_90": 3, "kp_180": 4,
             "impactList": [{"location": "STEREO A", "arrivalTime": "2026-10-24T00:00Z"}],
             "cmeInputs": [{"CMEID": "x"}]},
            {"estimatedShockArrivalTime": None, "impactList": None, "cmeInputs": []},
            {"estimatedShockArrivalTime": "2026-10-25T06:00Z"},  # same CME, another run
        ]
        f = donki.normalize({"data": {"WSAEnlilSimulations": sims, "CME": []}})
        self.assertEqual(f["earth_arrivals"], [{"arrival": "2026-10-25T06:00Z", "glancing": False,
                                                "minor": True, "kp_90": 3, "kp_180": 4}])

    def test_tec_empty_index_tolerated(self):
        f = tec.normalize({"index": [], "tile": None})
        self.assertFalse(f["available"])

    def test_tec_value_at_nearest_cell(self):
        tile = {"features": [
            {"geometry": {"type": "Point", "coordinates": [10.0, 0.0]},
             "properties": {"tec": 12}},
            {"geometry": {"type": "Point", "coordinates": [0.2, 0.2]},
             "properties": {"tec": 70}},
        ]}
        f = tec.normalize({"index": [{"time_tag": "t", "url": "/x"}], "tile": tile})
        self.assertEqual(f["tec_max"], 70)
        self.assertEqual(f["grid"], [[10.0, 0.0, 12.0, None], [0.2, 0.2, 70.0, None]])
        self.assertEqual(tec.tec_value_at(tile, 0.0, 0.0), 70)

    def test_tec_anomaly_only_where_observed(self):
        tile = {"features": [
            {"geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
             "properties": {"tec": 30, "anomaly": 14.0, "quality_flag": 5}},
            {"geometry": {"type": "Point", "coordinates": [40.0, 0.0]},
             "properties": {"tec": 30, "anomaly": 14.0, "quality_flag": 0}},
        ]}
        grid = tec.normalize({"index": [{"time_tag": "t", "url": "/x"}], "tile": tile})["grid"]
        self.assertEqual(tec.nearest_anomaly(grid, 0.0, 0.0), 14.0)
        self.assertIsNone(tec.nearest_anomaly(grid, 40.0, 0.0))  # no GNSS observations
        self.assertIsNone(tec.nearest_anomaly([[0.0, 0.0, 30.0]], 0.0, 0.0))  # old 3-column grid

    def test_ovation_grid_and_lookup(self):
        raw = {"Observation Time": "o", "Forecast Time": "f",
               "coordinates": [[0, 0, 0], [280, 44, 23], [100, -60, 5]]}
        f = ovation.normalize(raw)
        self.assertTrue(f["available"])
        self.assertEqual(f["grid"], [[280, 44, 23], [100, -60, 5]])
        self.assertEqual(f["aurora_max"], 23)
        self.assertEqual(ovation.aurora_at(f["grid"], 43.65, -79.6), 23)  # -79.6 E -> 280
        self.assertEqual(ovation.aurora_at(f["grid"], 0.0, 0.0), 0)
        self.assertIsNone(ovation.aurora_at([], 0.0, 0.0))
        self.assertFalse(ovation.normalize({})["available"])


if __name__ == "__main__":
    unittest.main()
