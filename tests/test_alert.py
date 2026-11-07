import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alert import evaluate  # noqa: E402

TODAY = "2026-11-07"


class EvaluateTest(unittest.TestCase):
    def keys(self, sp, fng, state=None):
        return [k for k, _ in evaluate(sp, fng, state or {}, TODAY, -5.0, 20.0)]

    def test_no_alert_in_normal_market(self):
        self.assertEqual(self.keys((5000, 5010, -0.2), (55, "greed")), [])

    def test_sp500_drop_at_threshold(self):
        self.assertEqual(self.keys((4750, 5000, -5.0), (50, "neutral")), ["sp500"])

    def test_fear_greed_at_threshold(self):
        self.assertEqual(self.keys((5000, 5000, 0.0), (20, "extreme fear")), ["fng"])

    def test_both(self):
        self.assertEqual(self.keys((4500, 5000, -10.0), (8, "extreme fear")), ["sp500", "fng"])

    def test_dedup_same_day(self):
        state = {"sp500": TODAY, "fng": TODAY}
        self.assertEqual(self.keys((4500, 5000, -10.0), (8, "extreme fear"), state), [])

    def test_alerts_again_next_day(self):
        state = {"sp500": "2026-11-06", "fng": "2026-11-06"}
        self.assertEqual(self.keys((4500, 5000, -10.0), (8, "x"), state), ["sp500", "fng"])

    def test_missing_data_is_skipped(self):
        self.assertEqual(self.keys(None, (10, "extreme fear")), ["fng"])
        self.assertEqual(self.keys((4500, 5000, -10.0), None), ["sp500"])


if __name__ == "__main__":
    unittest.main()
