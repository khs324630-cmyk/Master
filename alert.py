"""S&P 500 급락 / Fear & Greed 공포 구간 알림.

조건
  - S&P 500 지수가 전일 종가 대비 DROP_THRESHOLD(기본 -5%) 이하
  - CNN Fear & Greed Index가 FNG_THRESHOLD(기본 20) 이하
  - 버크셔 해서웨이 새 13F 공시 (brk.py)

알림 채널 (설정된 것 모두 사용)
  - 아이폰/브라우저 웹 푸시: PUSH_CONFIG  (웹앱의 '알림 켜기'에서 복사한 JSON, 여러 기기면 JSON 배열)
  - ntfy:                   NTFY_TOPIC  (선택: NTFY_SERVER, NTFY_TOKEN)

같은 조건은 한 번만 알립니다. S&P 500은 거래일마다, Fear & Greed는 미국 동부시간 하루마다 (state.json).

사용법
  python alert.py                      # 조건 확인 후 필요하면 알림
  python alert.py --out web/data.json  # 웹앱 대시보드용 데이터도 저장
  python alert.py --dry-run            # 알림 없이 결과만 출력
  python alert.py --test               # 테스트 알림 1건 전송
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import brk

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=3mo&interval=1d"
CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://edition.cnn.com/",
    "Origin": "https://edition.cnn.com",
}
ET = ZoneInfo("America/New_York")
APP_URL = os.environ.get("APP_URL", "https://khs324630-cmyk.github.io/Master/")
HISTORY_DAYS = 60
# VAPID 연락처: Apple/Google이 요구하는 형식 (https 출처 또는 mailto:)
VAPID_SUB = os.environ.get("VAPID_SUB") or "https://" + APP_URL.split("://", 1)[-1].split("/", 1)[0]


def http_json(url: str, data: dict | None = None, headers: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode() or "{}")


def et_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).date().isoformat()


# ---------------------------------------------------------------- 데이터 조회

def parse_sp500(raw: dict) -> dict:
    """Yahoo chart 응답 → {price, prev, pct, session, history}."""
    result = raw["chart"]["result"][0]
    meta = result["meta"]
    price = float(meta["regularMarketPrice"])
    session = et_date(meta["regularMarketTime"])
    closes = result["indicators"]["quote"][0]["close"]
    history = [
        {"d": et_date(t), "v": round(c, 2)}
        for t, c in zip(result["timestamp"], closes)
        if c is not None
    ]
    # 전일 종가 = 현재 거래일보다 앞선 마지막 종가
    earlier = [h["v"] for h in history if h["d"] < session]
    prev = earlier[-1] if earlier else float(meta["chartPreviousClose"])
    if history and history[-1]["d"] == session:
        history[-1]["v"] = round(price, 2)
    else:
        history.append({"d": session, "v": round(price, 2)})
    return {
        "price": price,
        "prev": prev,
        "pct": (price - prev) / prev * 100,
        "session": session,
        "history": history[-HISTORY_DAYS:],
    }


def parse_fear_greed(raw: dict) -> dict:
    """CNN graphdata 응답 → {score, rating, history}."""
    fg = raw["fear_and_greed"]
    by_day: dict[str, float] = {}
    for p in raw.get("fear_and_greed_historical", {}).get("data", []):
        by_day[et_date(p["x"] / 1000)] = round(float(p["y"]), 1)
    history = [{"d": d, "v": v} for d, v in sorted(by_day.items())]
    return {
        "score": float(fg["score"]),
        "rating": str(fg.get("rating", "")),
        "history": history[-HISTORY_DAYS:],
    }


def fetch_sp500() -> dict:
    return parse_sp500(http_json(YAHOO_URL, headers=BROWSER_HEADERS))


def fetch_fear_greed() -> dict:
    return parse_fear_greed(http_json(CNN_URL, headers=BROWSER_HEADERS))


# ---------------------------------------------------------------- 조건 판단

def evaluate(
    sp: dict | None,
    fng: dict | None,
    state: dict,
    today: str,
    drop_threshold: float,
    fng_threshold: float,
) -> list[tuple[str, str, dict]]:
    """보낼 알림 [(조건키, 중복방지 날짜, 알림)] 반환. 이미 보낸 조건은 제외."""
    alerts = []
    if sp is not None and sp["pct"] <= drop_threshold and state.get("sp500") != sp["session"]:
        alerts.append((
            "sp500",
            sp["session"],
            {
                "title": f"S&P 500 급락 {sp['pct']:.2f}%",
                "body": f"현재 {sp['price']:,.2f} (전일 종가 {sp['prev']:,.2f})\n기준: {drop_threshold:g}% 이하",
                "priority": 5,
                "tags": ["rotating_light", "chart_with_downwards_trend"],
            },
        ))
    if fng is not None and fng["score"] <= fng_threshold and state.get("fng") != today:
        alerts.append((
            "fng",
            today,
            {
                "title": f"Fear & Greed {fng['score']:.0f} ({fng['rating']})",
                "body": f"공포 탐욕 지수가 {fng['score']:.1f}로 기준({fng_threshold:g} 이하)에 도달했습니다.",
                "priority": 4,
                "tags": ["warning", "fearful"],
            },
        ))
    return alerts


# ---------------------------------------------------------------- 알림 채널

def load_push_configs() -> list[dict]:
    raw = os.environ.get("PUSH_CONFIG", "").strip()
    if not raw:
        return []
    data = json.loads(raw)
    return data if isinstance(data, list) else [data]


def send_webpush(alert: dict) -> int:
    """등록된 모든 기기에 웹 푸시. 성공한 기기 수 반환."""
    configs = load_push_configs()
    if not configs:
        return 0
    from py_vapid import Vapid
    from pywebpush import WebPushException, webpush

    payload = json.dumps({"title": alert["title"], "body": alert["body"], "url": APP_URL})
    sent = 0
    for i, cfg in enumerate(configs, 1):
        try:
            webpush(
                subscription_info=cfg["subscription"],
                data=payload,
                vapid_private_key=Vapid.from_raw(cfg["vapid_private_key"].encode()),
                vapid_claims={"sub": VAPID_SUB},
                ttl=24 * 60 * 60,
                headers={"Urgency": "high"},
            )
            sent += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            hint = " (구독이 만료됨: 웹앱에서 '알림 켜기'를 다시 해서 PUSH_CONFIG를 갱신하세요)" if status in (404, 410) else ""
            print(f"웹 푸시 실패 [기기 {i}] {status}: {e}{hint}", file=sys.stderr)
    return sent


def send_ntfy(alert: dict) -> int:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return 0
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {"Content-Type": "application/json"}
    if token := os.environ.get("NTFY_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    msg = {
        "topic": topic,
        "title": alert["title"],
        "message": alert["body"],
        "priority": alert.get("priority", 3),
        "tags": alert.get("tags", []),
        "click": APP_URL,
    }
    try:
        http_json(server, data=msg, headers=headers)
        return 1
    except urllib.error.URLError as e:
        print(f"ntfy 실패: {e}", file=sys.stderr)
        return 0


def notify(alert: dict) -> int:
    return send_webpush(alert) + send_ntfy(alert)


# ---------------------------------------------------------------- 상태 파일

def load_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def log_alert(state: dict, alert: dict) -> None:
    log = state.setdefault("log", [])
    log.append({"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "title": alert["title"]})
    state["log"] = log[-20:]


# ---------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="알림을 보내지 않고 출력만")
    parser.add_argument("--test", action="store_true", help="테스트 알림 전송")
    parser.add_argument("--out", help="웹앱용 data.json 저장 경로")
    args = parser.parse_args()

    if not (os.environ.get("PUSH_CONFIG") or os.environ.get("NTFY_TOPIC")):
        print("경고: PUSH_CONFIG / NTFY_TOPIC 둘 다 없어 알림을 보낼 곳이 없습니다.", file=sys.stderr)

    if args.test:
        n = notify({"title": "테스트 알림", "body": "알림 연결이 정상입니다.", "tags": ["white_check_mark"]})
        print(f"테스트 알림 전송: {n}곳")
        if not args.out:
            return 0 if n else 1

    drop_threshold = float(os.environ.get("DROP_THRESHOLD", "-5"))
    fng_threshold = float(os.environ.get("FNG_THRESHOLD", "20"))
    state_file = os.environ.get("STATE_FILE", "state.json")
    today = datetime.now(ET).date().isoformat()

    errors: dict[str, str] = {}
    sp = fng = None
    try:
        sp = fetch_sp500()
        print(f"S&P 500: {sp['price']:,.2f} (전일 {sp['prev']:,.2f}, {sp['pct']:+.2f}%, {sp['session']})")
    except Exception as e:  # noqa: BLE001
        errors["sp500"] = str(e)
        print(f"S&P 500 조회 실패: {e}", file=sys.stderr)
    try:
        fng = fetch_fear_greed()
        print(f"Fear & Greed: {fng['score']:.1f} ({fng['rating']})")
    except Exception as e:  # noqa: BLE001
        errors["fng"] = str(e)
        print(f"Fear & Greed 조회 실패: {e}", file=sys.stderr)

    state = load_json(state_file)
    alerts = evaluate(sp, fng, state, today, drop_threshold, fng_threshold)
    if not alerts:
        print("알림 조건에 해당하지 않습니다.")
    for key, mark, alert in alerts:
        if args.dry_run:
            print(f"[dry-run] {alert['title']}")
            continue
        n = notify(alert)
        print(f"알림 전송 ({n}곳): {alert['title']}")
        if n:
            state[key] = mark
            log_alert(state, alert)

    # 버크셔 해서웨이 13F 포트폴리오
    brk_cache = state.get("brk", {})
    try:
        brk_cache, brk_alert = brk.update(brk_cache)
        pf = brk_cache["portfolio"]
        print(f"버크셔 13F: {pf['quarter']} (공시 {pf['filed']}), {len(pf['holdings'])}종목")
        if brk_alert:
            if args.dry_run:
                print(f"[dry-run] {brk_alert['title']}")
            else:
                n = notify(brk_alert)
                print(f"알림 전송 ({n}곳): {brk_alert['title']}")
                log_alert(state, brk_alert)
        if not args.dry_run:
            state["brk"] = brk_cache
    except Exception as e:  # noqa: BLE001
        errors["brk"] = str(e)
        print(f"버크셔 13F 조회 실패: {e}", file=sys.stderr)

    if not args.dry_run:
        save_json(state_file, state)

    if args.out:
        save_json(args.out, {
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "thresholds": {"drop": drop_threshold, "fng": fng_threshold},
            "sp500": sp,
            "fng": fng,
            "brk": brk_cache.get("portfolio"),
            "errors": errors,
            "alerts": state.get("log", []),
        })

    # 시장 데이터 두 개가 모두 실패하면 워크플로가 실패로 표시되도록
    return 1 if {"sp500", "fng"} <= errors.keys() else 0


if __name__ == "__main__":
    sys.exit(main())
