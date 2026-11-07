"""버크셔 해서웨이 포트폴리오 추적 (SEC 13F-HR 공시).

- 최신 13F-HR과 직전 분기 13F-HR을 비교해 신규 / 확대 / 축소 / 전량 매도를 계산합니다.
- 새 13F가 올라오면 알림을 보냅니다 (분기마다 1번, 보통 2·5·8·11월 중순).
- SEC는 요청마다 연락처가 담긴 User-Agent를 요구합니다. 차단되면 SEC_USER_AGENT 변수에
  "이름 이메일" 형식으로 넣어 주세요.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import time
import urllib.error
import urllib.request
import zlib
import xml.etree.ElementTree as ET
from datetime import date

CIK = "1067983"  # Berkshire Hathaway Inc
SUBMISSIONS_URL = f"https://data.sec.gov/submissions/CIK{int(CIK):010d}.json"
ARCHIVE_URL = f"https://www.sec.gov/Archives/edgar/data/{CIK}/{{acc}}/"
CHECK_INTERVAL = 3 * 60 * 60  # SEC 조회는 3시간에 한 번이면 충분


def _ua() -> str:
    return os.environ.get("SEC_USER_AGENT") or "MarketAlert/1.0 (+https://github.com/khs324630-cmyk/Master)"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _ua(), "Accept-Encoding": "gzip, deflate"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            elif resp.headers.get("Content-Encoding") == "deflate":
                body = zlib.decompress(body)
            return body
    except urllib.error.HTTPError as e:
        raw = e.read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        text = re.sub(r"<[^>]+>", " ", raw.decode("utf-8", "replace"))
        detail = " ".join(text.split())[:400]
        raise RuntimeError(f"{e.code} {url} (UA={_ua()!r}) {detail}") from None


# ---------------------------------------------------------------- SEC 조회

def parse_filings(submissions: dict) -> list[dict]:
    """submissions JSON → 13F-HR 목록 (최신순)."""
    r = submissions["filings"]["recent"]
    out = []
    for form, acc, filed, period in zip(r["form"], r["accessionNumber"], r["filingDate"], r["reportDate"]):
        if form == "13F-HR":
            out.append({"accession": acc, "filed": filed, "period": period})
    return out


def parse_info_table(xml_bytes: bytes) -> list[dict]:
    """13F information table XML → 보유 종목 (CUSIP별 합산)."""
    root = ET.fromstring(xml_bytes)
    local = lambda el: el.tag.rsplit("}", 1)[-1]  # noqa: E731  네임스페이스 무시
    holdings: dict[str, dict] = {}
    for row in root.iter():
        if local(row) != "infoTable":
            continue
        f = {}
        for el in row.iter():
            if el.text and el.text.strip():
                f[local(el)] = el.text.strip()
        if f.get("putCall"):  # 옵션 포지션 제외
            continue
        cusip = f["cusip"].upper()
        h = holdings.setdefault(cusip, {
            "name": f.get("nameOfIssuer", cusip),
            "cls": f.get("titleOfClass", ""),
            "cusip": cusip,
            "value": 0,
            "shares": 0,
        })
        h["value"] += int(float(f.get("value", 0)))
        if f.get("sshPrnamtType", "SH") == "SH":
            h["shares"] += int(float(f.get("sshPrnamt", 0)))
    return list(holdings.values())


def fetch_filings() -> list[dict]:
    return parse_filings(json.loads(_get(SUBMISSIONS_URL)))


def fetch_holdings(accession: str) -> list[dict]:
    base = ARCHIVE_URL.format(acc=accession.replace("-", ""))
    items = json.loads(_get(base + "index.json"))["directory"]["item"]
    # 정보 테이블은 primary_doc.xml이 아닌 XML (이름이 공시마다 다름) → 큰 파일부터 시도
    xmls = sorted(
        (i for i in items if i["name"].lower().endswith(".xml")),
        key=lambda i: ("primary_doc" in i["name"].lower(), -int(i.get("size") or 0)),
    )
    for name in (i["name"] for i in xmls):
        time.sleep(0.2)
        holdings = parse_info_table(_get(base + name))
        if holdings:
            return holdings
    raise RuntimeError(f"{accession}: 13F 정보 테이블을 찾지 못했습니다")


# ---------------------------------------------------------------- 비교

def quarter_label(period: str) -> str:
    d = date.fromisoformat(period)
    return f"{d.year}년 {(d.month - 1) // 3 + 1}분기"


def compare(cur: list[dict], prev: list[dict] | None) -> dict:
    """현재/직전 분기 보유 종목 비교."""
    prev_by = {h["cusip"]: h for h in (prev or [])}
    total = sum(h["value"] for h in cur) or 1
    rows = []
    for h in sorted(cur, key=lambda h: h["value"], reverse=True):
        p = prev_by.get(h["cusip"])
        if prev is None:
            change, pct = "unknown", None
        elif p is None:
            change, pct = "new", None
        elif p["shares"] and h["shares"] != p["shares"]:
            pct = (h["shares"] - p["shares"]) / p["shares"] * 100
            change = "add" if pct > 0 else "trim"
        else:
            change, pct = "hold", 0.0
        rows.append({**h, "weight": h["value"] / total * 100, "change": change,
                     "shares_pct": None if pct is None else round(pct, 2)})
    cur_ids = {h["cusip"] for h in cur}
    sold = sorted((h for h in (prev or []) if h["cusip"] not in cur_ids), key=lambda h: h["value"], reverse=True)
    return {
        "total_value": sum(h["value"] for h in cur),
        "holdings": rows,
        "sold": [{"name": h["name"], "cls": h["cls"], "cusip": h["cusip"], "prev_value": h["value"]} for h in sold],
    }


def summarize(portfolio: dict) -> dict:
    """알림 문구."""
    by = lambda c: [h["name"] for h in portfolio["holdings"] if h["change"] == c]  # noqa: E731
    parts = []
    for label, names in (("신규", by("new")), ("전량 매도", [h["name"] for h in portfolio["sold"]]),
                         ("확대", by("add")), ("축소", by("trim"))):
        if names:
            shown = ", ".join(names[:3]) + (f" 외 {len(names) - 3}" if len(names) > 3 else "")
            parts.append(f"{label}: {shown}")
    return {
        "title": f"버크셔 13F 공시 ({portfolio['quarter']})",
        "body": "\n".join(parts) or "보유 종목 변화가 없습니다.",
        "priority": 3,
        "tags": ["briefcase"],
    }


# ---------------------------------------------------------------- 실행

def update(cache: dict, now: float | None = None) -> tuple[dict, dict | None]:
    """cache(이전 결과)를 받아 (최신 포트폴리오, 새 공시 알림 또는 None) 반환."""
    now = now or time.time()
    if cache.get("portfolio") and now - cache.get("checked_at", 0) < CHECK_INTERVAL:
        return cache, None

    filings = fetch_filings()
    if not filings:
        raise RuntimeError("13F-HR 공시를 찾지 못했습니다")
    latest = filings[0]
    old = cache.get("portfolio")
    if old and old.get("accession") == latest["accession"]:
        return {**cache, "checked_at": now}, None

    cur = fetch_holdings(latest["accession"])
    prev = fetch_holdings(filings[1]["accession"]) if len(filings) > 1 else None
    portfolio = {
        **compare(cur, prev),
        "accession": latest["accession"],
        "filed": latest["filed"],
        "period": latest["period"],
        "quarter": quarter_label(latest["period"]),
        "prev_period": filings[1]["period"] if len(filings) > 1 else None,
        "url": ARCHIVE_URL.format(acc=latest["accession"].replace("-", "")),
    }
    # 처음 실행 때는 알림 없이 저장만 (이미 지난 공시이므로)
    alert = summarize(portfolio) if old else None
    return {"portfolio": portfolio, "checked_at": now}, alert
