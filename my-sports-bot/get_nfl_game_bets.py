"""
Fetch recent bets (fills) for NFL game markets using the Polymarket Gamma API.

- Single-game mode: `python get_nfl_game_bets.py --game-id <market_id>`
- Batch mode: `python get_nfl_game_bets.py --all`

Batch mode mirrors the filters from `get_nfl_games.py` (NFL tag 100639, spreads/totals/moneyline)
and can be run on a schedule. When run with `--notify`, the script sends a Pushover alert to the
configured group when it detects a newly seen fill larger than USD $10,000.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from typing import Dict, Iterable, List

import pytz
import requests

NFL_GAME_TAG_ID = "100639"
FILL_LIMIT = 500
FILL_BATCH_SIZE = 100
PUSHOVER_GROUP_KEY = "ucdzy7t32br76dwht5qtz5mt7fg7n3"
PUSHOVER_API_TOKEN = "a75tq5kqignpk3p8ndgp66bske3bsi"
FILL_THRESHOLD_USD = 10_000
STATE_PATH = os.path.join("data", "last_fill_state.json")
FILL_ENDPOINT = "https://gamma-api.polymarket.com/fills"
MARKET_ENDPOINT = "https://gamma-api.polymarket.com/markets"
PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json"
SUPPORTED_TYPES = {"spreads", "totals", "moneyline"}

def ensure_data_dir() -> None:
    os.makedirs("data", exist_ok=True)

def fetch_fills_for_market(market_id: str, *, limit: int = FILL_LIMIT) -> List[Dict]:
    fills: List[Dict] = []
    offset = 0
    while len(fills) < limit:
        params = {
            "market": market_id,
            "limit": min(FILL_BATCH_SIZE, limit - len(fills)),
            "offset": offset,
        }
        resp = requests.get(FILL_ENDPOINT, params=params, timeout=10)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        fills.extend(batch)
        if len(batch) < params["limit"]:
            break
        offset += params["limit"]
    return fills

def fetch_active_nfl_game_markets() -> List[Dict]:
    markets: List[Dict] = []
    offset = 0
    limit = 100
    while True:
        params = {
            "tag_id": NFL_GAME_TAG_ID,
            "closed": "false",
            "limit": limit,
            "offset": offset,
        }
        resp = requests.get(MARKET_ENDPOINT, params=params, timeout=10)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for market in batch:
            if market.get("sportsMarketType") in SUPPORTED_TYPES:
                markets.append(market)
        if len(batch) < limit:
            break
        offset += limit
    return markets

def save_fills_to_file(fills: Iterable[Dict], path: str) -> None:
    ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(list(fills), f, indent=2, default=str)

def load_state() -> Dict[str, str]:
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state: Dict[str, str]) -> None:
    ensure_data_dir()
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def format_et(timestamp: str) -> str:
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    dt_utc = dt.replace(tzinfo=pytz.UTC)
    return dt_utc.astimezone(pytz.timezone("America/New_York")).strftime("%m/%d/%y %I:%M %p ET")

def fill_identifier(fill: Dict) -> str:
    return str(fill.get("id") or fill.get("_id") or fill.get("transactionHash") or fill)

def usd_size(fill: Dict) -> float:
    price = float(fill.get("price") or 0)
    size = float(fill.get("size") or fill.get("amount") or 0)
    notional = price * size
    if fill.get("quoteAmount") is not None:
        try:
            notional = float(fill.get("quoteAmount"))
        except (TypeError, ValueError):
            pass
    if fill.get("notional") is not None:
        try:
            notional = float(fill.get("notional"))
        except (TypeError, ValueError):
            pass
    return notional

def send_pushover(message: str) -> None:
    data = {
        "token": PUSHOVER_API_TOKEN,
        "user": PUSHOVER_GROUP_KEY,
        "message": message,
    }
    resp = requests.post(PUSHOVER_ENDPOINT, data=data, timeout=10)
    resp.raise_for_status()

def notify_new_large_fills(market: Dict, fills: List[Dict], state: Dict[str, str]) -> None:
    market_id = str(market.get("id"))
    last_seen = state.get(market_id)
    sorted_fills = sorted(fills, key=lambda f: f.get("timestamp") or f.get("createdAt") or "")
    for fill in sorted_fills:
        fid = fill_identifier(fill)
        if last_seen and fid <= last_seen:
            continue
        amount_usd = usd_size(fill)
        if amount_usd >= FILL_THRESHOLD_USD:
            ts = fill.get("timestamp") or fill.get("createdAt") or ""
            time_display = format_et(ts) if ts else "unknown time"
            outcome = fill.get("outcome") or fill.get("outcomeId") or "unknown"
            message = (
                f"New large bet for {market.get('question', 'NFL market')}\n"
                f"Outcome: {outcome}\n"
                f"Size: ${amount_usd:,.2f}\n"
                f"When: {time_display}"
            )
            send_pushover(message)
        state[market_id] = fid

def collect_for_single_market(market_id: str) -> None:
    fills = fetch_fills_for_market(market_id)
    save_path = os.path.join("data", f"market_{market_id}_fills.json")
    save_fills_to_file(fills, save_path)
    print(f"Saved {len(fills)} fills to {save_path}")

def collect_for_all_markets(send_notifications: bool = False) -> None:
    markets = fetch_active_nfl_game_markets()
    state = load_state()
    all_fills: Dict[str, List[Dict]] = {}
    for market in markets:
        market_id = market.get("id")
        if not market_id:
            continue
        fills = fetch_fills_for_market(str(market_id))
        all_fills[str(market_id)] = fills
        print(f"Fetched {len(fills)} fills for {market.get('slug', market_id)}")
        if send_notifications:
            notify_new_large_fills(market, fills, state)
    save_state(state)
    save_fills_to_file(all_fills, os.path.join("data", "nfl_game_fills.json"))
    print(f"Saved fills for {len(all_fills)} markets to data/nfl_game_fills.json")

def parse_args(args: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Polymarket fills for NFL games")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--game-id", help="Fetch fills for a single market ID")
    group.add_argument("--all", action="store_true", help="Fetch fills for all NFL game markets")
    parser.add_argument("--notify", action="store_true", help="Send Pushover alerts for new fills above $10k")
    return parser.parse_args(args)

def main() -> None:
    ensure_data_dir()
    args = parse_args(sys.argv[1:])
    if args.game_id:
        collect_for_single_market(args.game_id)
    elif args.all:
        collect_for_all_markets(send_notifications=args.notify)

if __name__ == "__main__":
    main()
