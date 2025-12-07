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
from typing import Dict, Iterable, List, Tuple, Union

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

StateEntry = Dict[str, Union[List[str], Dict[str, float]]]


def load_state() -> Dict[str, StateEntry]:
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        raw_state = json.load(f)
    # Backward compatibility: previous format stored last seen ID as a string
    state: Dict[str, StateEntry] = {}
    for market_id, entry in raw_state.items():
        if isinstance(entry, dict):
            seen_ids = entry.get("seen_ids") or []
            actor_totals = entry.get("actor_totals") or {}
        else:
            seen_ids = [entry] if isinstance(entry, str) else []
            actor_totals = {}
        state[str(market_id)] = {
            "seen_ids": [str(fid) for fid in seen_ids],
            "actor_totals": {str(k): float(v) for k, v in actor_totals.items()},
        }
    return state

def save_state(state: Dict[str, StateEntry]) -> None:
    ensure_data_dir()
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def format_et(timestamp: str) -> str:
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    dt_utc = dt.replace(tzinfo=pytz.UTC)
    return dt_utc.astimezone(pytz.timezone("America/New_York")).strftime("%m/%d/%y %I:%M %p ET")

def fill_identifier(fill: Dict) -> str:
    return str(fill.get("id") or fill.get("_id") or fill.get("transactionHash") or fill)

def fill_actor(fill: Dict) -> str:
    return str(
        fill.get("maker")
        or fill.get("taker")
        or fill.get("creator")
        or fill.get("user")
        or "unknown"
    )

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

def notify_new_large_fills(
    market: Dict, fills: List[Dict], state: Dict[str, StateEntry]
) -> None:
    market_id = str(market.get("id"))
    market_state = state.get(market_id, {})
    existing_ids = set(market_state.get("seen_ids") or [])
    existing_totals = dict(market_state.get("actor_totals") or {})
    sorted_fills = sorted(
        fills,
        key=lambda f: (f.get("timestamp") or f.get("createdAt") or "", fill_identifier(f)),
    )

    actor_totals: Dict[Tuple[str, str], float] = {}
    actor_counts: Dict[Tuple[str, str], int] = {}
    new_ids: List[str] = []

    for fill in sorted_fills:
        fid = fill_identifier(fill)
        if fid in existing_ids:
            continue
        new_ids.append(fid)
        actor = fill_actor(fill)
        outcome = str(fill.get("outcome") or fill.get("outcomeId") or "unknown")
        amount_usd = usd_size(fill)
        key = (actor, outcome)
        actor_totals[key] = actor_totals.get(key, 0.0) + amount_usd
        actor_counts[key] = actor_counts.get(key, 0) + 1

    updated_totals: Dict[str, float] = dict(existing_totals)

    for (actor, outcome), total_new in actor_totals.items():
        key_str = f"{actor}::{outcome}"
        prior_total = existing_totals.get(key_str, 0.0)
        cumulative_total = prior_total + total_new
        updated_totals[key_str] = cumulative_total

        if prior_total < FILL_THRESHOLD_USD <= cumulative_total:
            ts = (
                sorted_fills[-1].get("timestamp")
                or sorted_fills[-1].get("createdAt")
                or ""
            )
            time_display = format_et(ts) if ts else "unknown time"
            fills_count = actor_counts[(actor, outcome)]
            message = (
                f"New large bettor activity for {market.get('question', 'NFL market')}\n"
                f"Actor: {actor}\n"
                f"Outcome: {outcome}\n"
                f"Total size: ${cumulative_total:,.2f} across {fills_count} new fills (cumulative)\n"
                f"Last fill: {time_display}"
            )
            send_pushover(message)

    if new_ids:
        updated_ids = list(existing_ids) + new_ids
        # Keep the most recent IDs to avoid unbounded growth while preventing duplicate alerts
        state[market_id] = {
            "seen_ids": updated_ids[-FILL_LIMIT:],
            "actor_totals": updated_totals,
        }
    else:
        state[market_id] = {
            "seen_ids": list(existing_ids),
            "actor_totals": updated_totals,
        }

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
