import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import brk  # noqa: E402

NS = "http://www.sec.gov/edgar/document/thirteenf/informationtable"


def row(name, cusip, value, shares, put_call=None):
    pc = f"<putCall>{put_call}</putCall>" if put_call else ""
    return f"""<infoTable><nameOfIssuer>{name}</nameOfIssuer><titleOfClass>COM</titleOfClass>
      <cusip>{cusip}</cusip><value>{value}</value>
      <shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>{pc}
      <investmentDiscretion>DFND</investmentDiscretion></infoTable>"""


def table(*rows):
    return f'<?xml version="1.0"?><informationTable xmlns="{NS}">{"".join(rows)}</informationTable>'.encode()


class ParseTest(unittest.TestCase):
    def test_info_table_aggregates_by_cusip_and_skips_options(self):
        xml = table(
            row("APPLE INC", "037833100", 1000, 10),
            row("APPLE INC", "037833100", 500, 5),  # 다른 운용 주체 행 → 합산
            row("BANK AMER CORP", "060505104", 300, 30),
            row("SOME CO", "123456789", 99, 1, put_call="Put"),
        )
        h = {x["cusip"]: x for x in brk.parse_info_table(xml)}
        self.assertEqual(set(h), {"037833100", "060505104"})
        self.assertEqual((h["037833100"]["value"], h["037833100"]["shares"]), (1500, 15))

    def test_filings_only_original_13f(self):
        sub = {"filings": {"recent": {
            "form": ["4", "13F-HR/A", "13F-HR", "13F-HR"],
            "accessionNumber": ["a", "b", "c", "d"],
            "filingDate": ["2026-11-14"] * 4,
            "reportDate": ["", "2026-06-30", "2026-09-30", "2026-06-30"],
        }}}
        self.assertEqual([f["accession"] for f in brk.parse_filings(sub)], ["c", "d"])

    def test_quarter_label(self):
        self.assertEqual(brk.quarter_label("2026-09-30"), "2026년 3분기")
        self.assertEqual(brk.quarter_label("2026-12-31"), "2026년 4분기")


def h(name, cusip, value, shares):
    return {"name": name, "cls": "COM", "cusip": cusip, "value": value, "shares": shares}


PREV = [h("APPLE", "A", 600, 100), h("BOFA", "B", 300, 100), h("KO", "K", 100, 50), h("HP", "H", 50, 10)]
CUR = [h("APPLE", "A", 500, 80), h("BOFA", "B", 330, 110), h("KO", "K", 120, 50), h("NEWCO", "N", 50, 5)]


class CompareTest(unittest.TestCase):
    def test_changes(self):
        p = brk.compare(CUR, PREV)
        by = {x["cusip"]: x for x in p["holdings"]}
        self.assertEqual(by["A"]["change"], "trim")
        self.assertAlmostEqual(by["A"]["shares_pct"], -20.0)
        self.assertEqual(by["B"]["change"], "add")
        self.assertEqual(by["K"]["change"], "hold")
        self.assertEqual(by["N"]["change"], "new")
        self.assertEqual([s["cusip"] for s in p["sold"]], ["H"])
        self.assertEqual(p["holdings"][0]["cusip"], "A")  # 평가액 순
        self.assertAlmostEqual(sum(x["weight"] for x in p["holdings"]), 100.0)

    def test_summary_text(self):
        p = {**brk.compare(CUR, PREV), "quarter": "2026년 3분기"}
        a = brk.summarize(p)
        self.assertEqual(a["title"], "버크셔 13F 공시 (2026년 3분기)")
        self.assertIn("신규: NEWCO", a["body"])
        self.assertIn("전량 매도: HP", a["body"])
        self.assertIn("확대: BOFA", a["body"])
        self.assertIn("축소: APPLE", a["body"])


FILINGS = [
    {"accession": "0000950123-26-000002", "filed": "2026-11-14", "period": "2026-09-30"},
    {"accession": "0000950123-26-000001", "filed": "2026-08-14", "period": "2026-06-30"},
]


class UpdateTest(unittest.TestCase):
    def run_update(self, cache, now=10**9):
        hold = {FILINGS[0]["accession"]: CUR, FILINGS[1]["accession"]: PREV}
        with mock.patch.object(brk, "fetch_filings", return_value=FILINGS) as ff, \
             mock.patch.object(brk, "fetch_holdings", side_effect=hold.__getitem__) as fh:
            out = brk.update(cache, now)
        return out, ff.call_count, fh.call_count

    def test_first_run_stores_without_alert(self):
        (cache, alert), _, fh = self.run_update({})
        self.assertIsNone(alert)
        self.assertEqual(cache["portfolio"]["quarter"], "2026년 3분기")
        self.assertEqual(fh, 2)

    def test_new_filing_alerts(self):
        old = {"portfolio": {"accession": "old"}, "checked_at": 0}
        (cache, alert), _, _ = self.run_update(old)
        self.assertIsNotNone(alert)
        self.assertEqual(cache["portfolio"]["accession"], FILINGS[0]["accession"])

    def test_same_filing_no_refetch(self):
        old = {"portfolio": {"accession": FILINGS[0]["accession"]}, "checked_at": 0}
        (cache, alert), ff, fh = self.run_update(old)
        self.assertIsNone(alert)
        self.assertEqual((ff, fh), (1, 0))

    def test_throttled(self):
        old = {"portfolio": {"accession": "x"}, "checked_at": 10**9 - 60}
        (_, alert), ff, _ = self.run_update(old)
        self.assertEqual((alert, ff), (None, 0))


if __name__ == "__main__":
    unittest.main()
