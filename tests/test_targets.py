import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import alert  # noqa: E402


def device(name, drop, fng):
    return {"subscription": {"endpoint": f"https://push.example/{name}", "keys": {}},
            "vapid_private_key": "x", "drop": drop, "fng": fng}


SP = {"price": 96.0, "prev": 100.0, "pct": -4.0, "session": "2026-11-06", "history": []}
FNG = {"score": 12.0, "rating": "extreme fear", "history": []}


class PerDeviceThresholdTest(unittest.TestCase):
    def run_main(self, configs, state_path):
        sent = []

        def fake_push(a, cfgs=None):
            sent.append((cfgs[0]["subscription"]["endpoint"].rsplit("/", 1)[1], a["title"]))
            return 1

        env = {"PUSH_CONFIG": json.dumps(configs), "STATE_FILE": state_path, "NTFY_TOPIC": ""}
        with mock.patch.dict(os.environ, env), \
             mock.patch.object(alert, "fetch_sp500", return_value=SP), \
             mock.patch.object(alert, "fetch_fear_greed", return_value=FNG), \
             mock.patch.object(alert.brk, "update", side_effect=RuntimeError("skip")), \
             mock.patch.object(alert, "send_webpush", side_effect=fake_push), \
             mock.patch.object(sys, "argv", ["alert.py"]):
            alert.main()
        return sent

    def test_each_device_uses_own_thresholds_and_dedups(self):
        configs = [device("a", -3, 10), device("b", -6, 15)]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")
            sent = self.run_main(configs, path)
            # a: S&P -4% ≤ -3% → 알림, F&G 12 > 10 → 없음 / b: -4% > -6% → 없음, 12 ≤ 15 → 알림
            self.assertEqual(sorted((dev, t.split()[0]) for dev, t in sent), [("a", "S&P"), ("b", "Fear")])
            # 같은 날 다시 실행 → 중복 알림 없음
            self.assertEqual(self.run_main(configs, path), [])
            # 기기 a 제거 → 상태에서 정리
            self.run_main([configs[1]], path)
            with open(path) as f:
                self.assertEqual(len(json.load(f)["targets"]), 1)


if __name__ == "__main__":
    unittest.main()
