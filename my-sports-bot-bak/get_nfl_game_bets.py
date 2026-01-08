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

# #region agent log
LOG_PATH = "/Users/td/Code/polymarket-bots/my-sports-bot/.cursor/debug.log"
def log_debug(location, message, data, hypothesis_id=None):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "location": location,
                "message": message,
                "data": data,
                "sessionId": "debug-session",
                "runId": "initial",
                "hypothesisId": hypothesis_id or "A"
            }
            f.write(json.dumps(entry) + "\n")
    except: pass
# #endregion

NFL_GAME_TAG_ID = "100639"
FILL_LIMIT = 500
FILL_BATCH_SIZE = 100
PUSHOVER_GROUP_KEY = "ucdzy7t32br76dwht5qtz5mt7fg7n3"
PUSHOVER_API_TOKEN = "a75tq5kqignpk3p8ndgp66bske3bsi"
FILL_THRESHOLD_USD = 10_000
STATE_PATH = os.path.join("data", "last_fill_state.json")
FILL_ENDPOINT = "https://data-api.polymarket.com/trades"
MARKET_ENDPOINT = "https://gamma-api.polymarket.com/markets"
PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json"
SUPPORTED_TYPES = {"spreads", "totals", "moneyline"}

def ensure_data_dir() -> None:
    os.makedirs("data", exist_ok=True)

def fetch_fills_for_market(market_id: str, *, limit: int = FILL_LIMIT) -> List[Dict]:
    # #region agent log
    log_debug("get_nfl_game_bets.py:54", "fetch_fills_for_market entry", {"market_id": market_id, "limit": limit, "endpoint": FILL_ENDPOINT}, "A")
    # #endregion
    # Fetch market details to get conditionId hex string
    condition_id_hex = None
    try:
        market_resp = requests.get(f"{MARKET_ENDPOINT}/{market_id}", timeout=10)
        # #region agent log
        log_debug("get_nfl_game_bets.py:59", "Fetching market details", {"status_code": market_resp.status_code, "url": f"{MARKET_ENDPOINT}/{market_id}"}, "C")
        # #endregion
        if market_resp.status_code == 200:
            market_data = market_resp.json()
            condition_id_hex = market_data.get("conditionId")
            # #region agent log
            log_debug("get_nfl_game_bets.py:64", "Market structure analysis", {
                "market_id": market_id,
                "condition_id": condition_id_hex,
            }, "C")
            # #endregion
    except Exception as e:
        # #region agent log
        log_debug("get_nfl_game_bets.py:71", "Error fetching market details", {"error": str(e)}, "C")
        # #endregion
        pass
    
    fills: List[Dict] = []
    offset = 0
    endpoint = FILL_ENDPOINT
    while len(fills) < limit:
        # Use 'market' parameter with conditionId hex string (proven to work from logs)
        if condition_id_hex:
            params = {
                "market": condition_id_hex,
                "limit": min(FILL_BATCH_SIZE, limit - len(fills)),
                "offset": offset,
            }
        else:
            # Fallback: try condition_id with numeric market ID
            params = {
                "condition_id": market_id,
            "limit": min(FILL_BATCH_SIZE, limit - len(fills)),
            "offset": offset,
        }
        # #region agent log
        param_key = "market" if condition_id_hex else "condition_id"
        param_val = condition_id_hex if condition_id_hex else market_id
        full_url = f"{endpoint}?{param_key}={param_val}&limit={params['limit']}&offset={offset}"
        log_debug("get_nfl_game_bets.py:85", "Request URL and params", {"url": full_url, "params": params, "endpoint_base": endpoint}, "A")
        # #endregion
        resp = requests.get(endpoint, params=params, timeout=10)
        # #region agent log
        log_debug("get_nfl_game_bets.py:89", "Response received", {"status_code": resp.status_code, "headers": dict(resp.headers), "url": resp.url}, "A")
        try:
            resp_body = resp.text[:1000] if resp.text else "empty"
            log_debug("get_nfl_game_bets.py:92", "Response body preview", {"body_preview": resp_body, "content_type": resp.headers.get("Content-Type")}, "A")
        except: pass
        # #endregion
        if resp.status_code == 404:
            # #region agent log
            log_debug("get_nfl_game_bets.py:79", "404 error detected, trying market parameter with conditionId", {"original_url": resp.url, "market_id": market_id}, "C")
            # #endregion
            # Try fetching market details to get conditionId hex, then use 'market' parameter
            try:
                market_resp = requests.get(f"{MARKET_ENDPOINT}/{market_id}", timeout=10)
                # #region agent log
                log_debug("get_nfl_game_bets.py:85", "Fetching market details", {"status_code": market_resp.status_code, "url": f"{MARKET_ENDPOINT}/{market_id}"}, "C")
                # #endregion
                if market_resp.status_code == 200:
                    market_data = market_resp.json()
                    condition_id = market_data.get("conditionId")
                    # #region agent log
                    log_debug("get_nfl_game_bets.py:90", "Market structure analysis", {
                        "market_id": market_id,
                        "condition_id": condition_id,
                    }, "C")
                    # #endregion
                    if condition_id:
                        # Try with 'market' parameter using conditionId hex
                        fallback_params = {"market": condition_id, "limit": params["limit"], "offset": offset}
                        # #region agent log
                        log_debug("get_nfl_game_bets.py:99", "Trying market parameter with conditionId", {"params": fallback_params, "endpoint": endpoint}, "C")
                        # #endregion
                        fallback_resp = requests.get(endpoint, params=fallback_params, timeout=10)
                        # #region agent log
                        log_debug("get_nfl_game_bets.py:103", "Fallback response", {"status_code": fallback_resp.status_code, "url": fallback_resp.url}, "C")
                        # #endregion
                        if fallback_resp.status_code == 200:
                            resp = fallback_resp
                            params = fallback_params
            except Exception as e:
                # #region agent log
                log_debug("get_nfl_game_bets.py:110", "Error in fallback", {"error": str(e)}, "C")
                # #endregion
                pass
        # #region agent log
        log_debug("get_nfl_game_bets.py:108", "Final response status", {"status_code": resp.status_code, "final_url": resp.url}, "A")
        # #endregion
        resp.raise_for_status()
        batch = resp.json()
        # #region agent log
        log_debug("get_nfl_game_bets.py:47", "Parsed JSON response", {"batch_size": len(batch) if batch else 0, "is_list": isinstance(batch, list)}, "A")
        # #endregion
        if not batch:
            break
        fills.extend(batch)
        if len(batch) < params["limit"]:
            break
        offset += params["limit"]
    # #region agent log
    log_debug("get_nfl_game_bets.py:54", "fetch_fills_for_market exit", {"total_fills": len(fills)}, "A")
    # #endregion
    return fills

def fetch_active_nfl_game_markets() -> List[Dict]:
    # #region agent log
    log_debug("get_nfl_game_bets.py:168", "fetch_active_nfl_game_markets entry", {"tag_id": NFL_GAME_TAG_ID, "supported_types": list(SUPPORTED_TYPES)}, "A")
    # #endregion
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
        # #region agent log
        log_debug("get_nfl_game_bets.py:179", "Batch received", {"batch_size": len(batch) if batch else 0, "offset": offset}, "A")
        # #endregion
        if not batch:
            break
        for market in batch:
            sports_type = market.get("sportsMarketType")
            slug = market.get("slug", "").lower()
            market_id = market.get("id")
            events = market.get("events", [])
            
            # Check if it's a supported sports market type
            if sports_type not in SUPPORTED_TYPES:
                continue
            
            # NFL filtering: check slug or events (matching get_nfl_games.py logic)
            is_nfl = False
            if slug.startswith("nfl-"):
                is_nfl = True
            elif events:
                for event in events:
                    series_slug = event.get("seriesSlug", "").lower()
                    if "nfl" in series_slug:
                        is_nfl = True
                        break
            
            # #region agent log
            log_debug("get_nfl_game_bets.py:186", "Market check", {
                "market_id": market_id,
                "sports_type": sports_type,
                "slug": slug[:50] if slug else None,
                "slug_starts_nfl": slug.startswith("nfl-") if slug else False,
                "is_nfl": is_nfl,
                "in_supported_types": True
            }, "A")
            # #endregion
            
            if is_nfl:
                # #region agent log
                log_debug("get_nfl_game_bets.py:207", "NFL market added", {
                    "market_id": market_id,
                    "slug": slug[:50] if slug else None
                }, "H1")
                # #endregion
                markets.append(market)
        if len(batch) < limit:
            break
        offset += limit
    # #region agent log
    log_debug("get_nfl_game_bets.py:199", "fetch_active_nfl_game_markets exit", {"total_markets": len(markets)}, "A")
    # #endregion
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

def format_et(timestamp: Union[str, int, float]) -> str:
    # #region agent log
    log_debug("get_nfl_game_bets.py:252", "format_et entry", {"timestamp": timestamp, "timestamp_type": type(timestamp).__name__}, "H2")
    # #endregion
    if isinstance(timestamp, (int, float)):
        # #region agent log
        log_debug("get_nfl_game_bets.py:256", "Numeric timestamp detected", {"timestamp": timestamp, "is_large": timestamp > 1e10}, "H2")
        # #endregion
        # Handle Unix timestamp (seconds or milliseconds)
        ts_seconds = float(timestamp)
        if ts_seconds > 1e10:  # Likely milliseconds
            ts_seconds = ts_seconds / 1000
        dt = datetime.fromtimestamp(ts_seconds, tz=pytz.UTC)
    else:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    dt_utc = dt.replace(tzinfo=pytz.UTC) if dt.tzinfo is None else dt
    result = dt_utc.astimezone(pytz.timezone("America/New_York")).strftime("%m/%d/%y %I:%M %p ET")
    # #region agent log
    log_debug("get_nfl_game_bets.py:265", "format_et exit", {"result": result}, "H2")
    # #endregion
    return result

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
            last_fill = sorted_fills[-1]
            ts_raw = last_fill.get("timestamp") or last_fill.get("createdAt") or ""
            # #region agent log
            log_debug("get_nfl_game_bets.py:313", "Timestamp extraction", {
                "ts_raw": ts_raw,
                "ts_type": type(ts_raw).__name__,
                "has_timestamp": "timestamp" in last_fill,
                "has_createdAt": "createdAt" in last_fill,
                "timestamp_value": last_fill.get("timestamp"),
                "createdAt_value": last_fill.get("createdAt")
            }, "H2")
            # #endregion
            ts = ts_raw
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
    # #region agent log
    log_debug("get_nfl_game_bets.py:221", "collect_for_single_market entry", {"market_id": market_id, "market_id_type": type(market_id).__name__}, "A")
    # #endregion
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
