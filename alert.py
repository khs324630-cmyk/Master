"""S&P 500 급락 / Fear & Greed 공포 구간 알림 (ntfy).

조건
  - S&P 500 지수가 전일 종가 대비 DROP_THRESHOLD(기본 -5%) 이하
  - CNN Fear & Greed Index가 FNG_THRESHOLD(기본 20) 이하

각 조건은 미국 동부시간 기준 하루에 한 번만 알립니다 (state.json).

환경 변수
  NTFY_TOPIC      (필수) 구독할 ntfy 토픽 이름
  NTFY_SERVER     ntfy 서버 주소, 기본 https://ntfy.sh
  NTFY_TOKEN      비공개 서버/토픽용 액세스 토큰 (선택)
  DROP_THRESHOLD  급락 기준(%), 기본 -5
  FNG_THRESHOLD   공포 지수 기준, 기본 20
  STATE_FILE      중복 방지 상태 파일, 기본 state.json

사용법
  python alert.py            # 조건 확인 후 필요하면 알림
  python alert.py --dry-run  # 알림 없이 결과만 출력
  python alert.py --test     # 테스트 알림 1건 전송
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=1d&interval=1d"
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


def http_json(url: str, data: dict | None = None, headers: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def fetch_sp500() -> tuple[float, float, float]:
    """(현재가, 전일 종가, 변동률 %) 반환."""
    meta = http_json(YAHOO_URL, headers=BROWSER_HEADERS)["chart"]["result"][0]["meta"]
    price = float(meta["regularMarketPrice"])
    prev = float(meta.get("chartPreviousClose") or meta["previousClose"])
    return price, prev, (price - prev) / prev * 100


def fetch_fear_greed() -> tuple[float, str]:
    """(점수, 등급) 반환."""
    fg = http_json(CNN_URL, headers=BROWSER_HEADERS)["fear_and_greed"]
    return float(fg["score"]), str(fg.get("rating", ""))


def load_state(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(path: str, state: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def evaluate(
    sp: tuple[float, float, float] | None,
    fng: tuple[float, str] | None,
    state: dict,
    today: str,
    drop_threshold: float,
    fng_threshold: float,
) -> list[tuple[str, dict]]:
    """보낼 알림 목록 [(조건키, 알림 내용)] 반환. 오늘 이미 보낸 조건은 제외."""
    alerts = []
    if sp is not None:
        price, prev, pct = sp
        if pct <= drop_threshold and state.get("sp500") != today:
            alerts.append((
                "sp500",
                {
                    "title": f"S&P 500 급락 {pct:.2f}%",
                    "message": f"현재 {price:,.2f} (전일 종가 {prev:,.2f})\n기준: {drop_threshold}% 이하",
                    "priority": 5,
                    "tags": ["rotating_light", "chart_with_downwards_trend"],
                },
            ))
    if fng is not None:
        score, rating = fng
        if score <= fng_threshold and state.get("fng") != today:
            alerts.append((
                "fng",
                {
                    "title": f"Fear & Greed {score:.0f} ({rating})",
                    "message": f"공포 탐욕 지수가 {score:.1f}로 기준({fng_threshold:g} 이하)에 도달했습니다.",
                    "priority": 4,
                    "tags": ["warning", "fearful"],
                },
            ))
    return alerts


def send_ntfy(alert: dict) -> None:
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        raise SystemExit("NTFY_TOPIC 환경 변수가 없습니다.")
    headers = {"Content-Type": "application/json"}
    if token := os.environ.get("NTFY_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    # JSON 발행 방식: 한글 제목을 HTTP 헤더에 넣지 않아도 됨
    http_json(server, data={"topic": topic, **alert}, headers=headers)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="알림을 보내지 않고 출력만")
    parser.add_argument("--test", action="store_true", help="테스트 알림 전송")
    args = parser.parse_args()

    if args.test:
        send_ntfy({"title": "테스트 알림", "message": "ntfy 연결이 정상입니다.", "tags": ["white_check_mark"]})
        print("테스트 알림을 보냈습니다.")
        return 0

    drop_threshold = float(os.environ.get("DROP_THRESHOLD", "-5"))
    fng_threshold = float(os.environ.get("FNG_THRESHOLD", "20"))
    state_file = os.environ.get("STATE_FILE", "state.json")
    today = datetime.now(ET).date().isoformat()

    errors = 0
    sp = fng = None
    try:
        sp = fetch_sp500()
        print(f"S&P 500: {sp[0]:,.2f} (전일 {sp[1]:,.2f}, {sp[2]:+.2f}%)")
    except Exception as e:  # noqa: BLE001
        errors += 1
        print(f"S&P 500 조회 실패: {e}", file=sys.stderr)
    try:
        fng = fetch_fear_greed()
        print(f"Fear & Greed: {fng[0]:.1f} ({fng[1]})")
    except Exception as e:  # noqa: BLE001
        errors += 1
        print(f"Fear & Greed 조회 실패: {e}", file=sys.stderr)

    state = load_state(state_file)
    alerts = evaluate(sp, fng, state, today, drop_threshold, fng_threshold)
    if not alerts:
        print("알림 조건에 해당하지 않습니다.")
    for key, alert in alerts:
        if args.dry_run:
            print(f"[dry-run] {alert['title']}")
            continue
        send_ntfy(alert)
        state[key] = today
        print(f"알림 전송: {alert['title']}")
    if not args.dry_run:
        save_state(state_file, state)

    # 두 데이터 모두 실패하면 워크플로가 실패로 표시되도록
    return 1 if errors == 2 else 0


if __name__ == "__main__":
    sys.exit(main())
