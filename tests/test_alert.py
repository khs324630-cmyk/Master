import os
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alert import evaluate, parse_fear_greed, parse_sp500  # noqa: E402

ET = ZoneInfo("America/New_York")
TODAY = "2026-11-06"


def ts(day, hour=16):
    return datetime.fromisoformat(f"{day}T{hour:02d}:00").replace(tzinfo=ET).timestamp()


def sp(pct, session=TODAY):
    return {"price": 100 + pct, "prev": 100.0, "pct": pct, "session": session}


def fg(score):
    return {"score": score, "rating": "x"}


class EvaluateTest(unittest.TestCase):
    def keys(self, s, f, state=None):
        return [k for k, _, _ in evaluate(s, f, state or {}, TODAY, -5.0, 20.0)]

    def test_no_alert_in_normal_market(self):
        self.assertEqual(self.keys(sp(-0.2), fg(55)), [])

    def test_thresholds_inclusive(self):
        self.assertEqual(self.keys(sp(-5.0), fg(20)), ["sp500", "fng"])
        self.assertEqual(self.keys(sp(-4.99), fg(20.1)), [])

    def test_dedup(self):
        state = {"sp500": TODAY, "fng": TODAY}
        self.assertEqual(self.keys(sp(-10), fg(8), state), [])

    def test_sp500_dedup_by_session_not_calendar_day(self):
        # 금요일 급락 → 토요일 실행 시 같은 거래일이므로 다시 알리지 않음
        state = {"sp500": "2026-11-06"}
        alerts = evaluate(sp(-6, "2026-11-06"), None, state, "2026-11-07", -5, 20)
        self.assertEqual(alerts, [])

    def test_alerts_again_on_new_day(self):
        state = {"sp500": "2026-11-05", "fng": "2026-11-05"}
        self.assertEqual(self.keys(sp(-10), fg(8), state), ["sp500", "fng"])

    def test_missing_data_is_skipped(self):
        self.assertEqual(self.keys(None, fg(10)), ["fng"])
        self.assertEqual(self.keys(sp(-10), None), ["sp500"])


class ParseTest(unittest.TestCase):
    def test_parse_sp500_intraday(self):
        raw = {"chart": {"result": [{
            "meta": {"regularMarketPrice": 4750.0, "regularMarketTime": ts("2026-11-06", 11),
                     "chartPreviousClose": 1.0},
            "timestamp": [ts("2026-11-04", 9), ts("2026-11-05", 9), ts("2026-11-06", 9)],
            "indicators": {"quote": [{"close": [4900.0, 5000.0, None]}]},
        }]}}
        r = parse_sp500(raw)
        self.assertEqual(r["prev"], 5000.0)
        self.assertAlmostEqual(r["pct"], -5.0)
        self.assertEqual(r["session"], "2026-11-06")
        self.assertEqual(r["history"][-1], {"d": "2026-11-06", "v": 4750.0})
        self.assertEqual(len(r["history"]), 3)

    def test_parse_fear_greed(self):
        raw = {"fear_and_greed": {"score": 18.4, "rating": "extreme fear"},
               "fear_and_greed_historical": {"data": [
                   {"x": ts("2026-11-05") * 1000, "y": 25.0},
                   {"x": ts("2026-11-06") * 1000, "y": 18.4}]}}
        r = parse_fear_greed(raw)
        self.assertEqual(r["score"], 18.4)
        self.assertEqual([h["d"] for h in r["history"]], ["2026-11-05", "2026-11-06"])


if __name__ == "__main__":
    unittest.main()
