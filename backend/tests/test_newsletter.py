import datetime as dt
import tempfile
import unittest

from backend import newsletter
from backend.store import Store

PKG = {"period": "2026-09", "window": ["2026-09-01", "2026-09-30"],
       "aggregated_at": "2026-10-01T00:05:00Z",
       "donki_counts": {"CME": 12, "GST": 2, "FLR": 40, "SEP": 1, "IPS": 3, "HSS": 2},
       "top_events": [{"date": "2026-09-10", "type": "Flare", "detail": "M2.1"}],
       "kyoto_dst": {"days": 30, "min_dst": -82, "storm_days_dst_le_-50": 3},
       "gfz_kp": {"days": 30, "max_kp": 6.0, "daily_max_kp": [2.0, 6.0, 3.0]},
       "omni": None, "sources": {"donki": "ok"}, "notes": []}


class TestNewsletter(unittest.TestCase):
    def test_last_complete_month(self):
        w = newsletter.last_complete_month(dt.date(2026, 10, 30))
        self.assertEqual((w["period"], w["end"]), ("2026-09", "2026-09-30"))
        w = newsletter.last_complete_month(dt.date(2026, 1, 15))
        self.assertEqual(w["period"], "2025-12")

    def test_validate_draft(self):
        self.assertEqual(newsletter.validate_draft("Max Kp 6.0", PKG), [])
        self.assertEqual(newsletter.validate_draft("Kp hit 999", PKG), [999.0])

    def test_chart_svg(self):
        svg = newsletter.render_chart_svg(PKG)
        self.assertIn("Daily max Kp", svg)
        self.assertIsNone(newsletter.render_chart_svg({"period": "x", "gfz_kp": None}))

    def test_template_draft_numbers_valid(self):
        md = newsletter._template_draft(PKG)
        self.assertEqual(newsletter.validate_draft(md, PKG), [])

    def test_write_draft_reports_attempts(self):
        attempts = []
        md, source = newsletter.write_draft(PKG, _attempts=attempts)
        self.assertEqual(source, "template")
        self.assertTrue(any("skipped" in str(a) for a in attempts))

    def test_compact_package_keeps_key_numbers(self):
        b = newsletter.compact_package(PKG)
        self.assertEqual(b["max_kp"], 6.0)
        self.assertEqual(b["min_dst"], -82)
        self.assertLessEqual(len(b["top_events"]), 6)
        self.assertNotIn("daily_max_kp", b)

    def test_retry_then_success(self):
        import json as _json
        import os as _os
        import urllib.request as _ureq

        calls = []

        class _R:
            def __init__(self, payload):
                self._p = payload

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return _json.dumps(self._p).encode()

        def fake(body):
            calls.append(1)
            if len(calls) < 3:
                return _R({"choices": [{"message": {"content": None},
                                        "finish_reason": "length"}]})
            return _R({"choices": [{"message": {"content": "Max Kp 6.0."},
                                    "finish_reason": "stop"}]})

        _os.environ["BASETEN_API_KEY"] = "k"
        _os.environ["BASETEN_MODEL"] = "m"
        real = _ureq.urlopen
        _ureq.urlopen = lambda req, timeout=None: fake(req)
        try:
            attempts = []
            md, source = newsletter.write_draft(PKG, _attempts=attempts)
        finally:
            _ureq.urlopen = real
            del _os.environ["BASETEN_API_KEY"]
            del _os.environ["BASETEN_MODEL"]
        self.assertEqual(source, "baseten")
        self.assertIn("Max Kp", md)
        self.assertEqual(len(calls), 3)
        self.assertTrue(any("empty content (try 1" in str(a) for a in attempts))

    def test_empty_content_recorded_not_crash(self):
        import json as _json
        import os as _os
        import urllib.request as _ureq

        class _R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return _json.dumps(
                    {"choices": [{"message": {"content": None},
                                  "finish_reason": "stop"}]}).encode()

        _os.environ["BASETEN_API_KEY"] = "k"
        _os.environ["BASETEN_MODEL"] = "m"
        real = _ureq.urlopen
        _ureq.urlopen = lambda *a, **k: _R()
        try:
            attempts = []
            md, source = newsletter.write_draft(PKG, _attempts=attempts)
        finally:
            _ureq.urlopen = real
            del _os.environ["BASETEN_API_KEY"]
            del _os.environ["BASETEN_MODEL"]
        self.assertEqual(source, "template")
        self.assertTrue(any("empty content" in str(a) for a in attempts))

    def test_generate_and_store(self):
        tmp = tempfile.mkdtemp()
        store = Store(f"{tmp}/t.db")
        orig = newsletter.collect
        newsletter.collect = lambda w: dict(PKG)
        try:
            out = newsletter.generate(store, period="2026-09")
        finally:
            newsletter.collect = orig
        self.assertEqual(out["period"], "2026-09")
        rows = store.list_newsletters()
        self.assertEqual(len(rows), 1)
        got = store.get_newsletter(out["id"])
        self.assertIn("2026-09", got["markdown"])
        self.assertIn("Daily max Kp", got["chart_svg"])


if __name__ == "__main__":
    unittest.main()
