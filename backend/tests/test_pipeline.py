import unittest

from backend.pipeline import run_pipeline

KP_RAW = {
    "kp3": [{"time_tag": "2026-10-20T00:00:00", "Kp": 2.0,
             "a_running": 7, "station_count": 8}],
    "kp1m": [{"time_tag": "t", "estimated_kp": 0.67, "kp": "1M"}],
    "forecast": [{"time_tag": "t", "kp": 5.0, "observed": "predicted"}],
    "scales": {"0": {"G": {"Scale": "0"}, "R": {}, "S": {}}},
}


class TestPipelineFetchers(unittest.TestCase):
    def test_fetcher_override_replaces_network_fetch(self):
        seen = {}

        def fake(env=None):
            seen["env"] = env
            return KP_RAW

        cfg = {"order": ["kp"], "providers": {"kp": {"enabled": True, "stale_after": 10}}}
        snap = run_pipeline(env={"x": 1}, config=cfg, now="2026-10-29T00:00:00Z",
                            fetchers={"kp": fake})
        self.assertEqual(seen["env"], {"x": 1})
        self.assertEqual(snap["now"]["kp"], 2.0)
        self.assertEqual(snap["fetched_at"], "2026-10-29T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
