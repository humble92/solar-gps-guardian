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
