#!/usr/bin/env python3
"""
UFC Large Wager Monitor via Polymarket CLOB WebSocket

Monitors all markets for a UFC event and sends Pushover notifications
when large wagers are detected.

Usage:
    python monitor_ufc_large_wagers.py <event_slug> [--threshold <usd>]

Example:
    python monitor_ufc_large_wagers.py ufc-jus3-pad-2026-01-24 --threshold 5000

References:
- Gamma API (markets): https://docs.polymarket.com/api-reference/core/get-market
- WebSocket Overview: https://docs.polymarket.com/developers/CLOB/websocket/wss-overview
- Market Channel: https://docs.polymarket.com/developers/CLOB/websocket/market-channel
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
import textwrap

import requests
from dotenv import load_dotenv
from websocket import create_connection, WebSocketConnectionClosedException

load_dotenv()

# === API Endpoints ===
GAMMA_API = "https://gamma-api.polymarket.com"
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json"

# === Default Settings ===
DEFAULT_USD_THRESHOLD = 5000.0
LOG_DIR = "logs"


def send_pushover(message: str, url: str = None, title: str = None) -> None:
    """Send a Pushover notification."""
    token = os.environ.get("PUSHOVER_API_TOKEN")
    user = os.environ.get("PUSHOVER_GROUP_KEY")
    if not token or not user:
        print("[WARN] Pushover credentials not found in env, skipping notification")
        return
    data = {"token": token, "user": user, "message": message, "html": 1}
    if title:
        data["title"] = title
    if url:
        data["url"] = url
        data["url_title"] = "View Market"
    try:
        resp = requests.post(PUSHOVER_ENDPOINT, data=data, timeout=10)
        if resp.ok:
            print("[INFO] Pushover notification sent")
        else:
            print(f"[WARN] Pushover failed: {resp.status_code}")
    except Exception as e:
        print(f"[ERROR] Pushover error: {e}")


def log_event(log_file: str, entry: str) -> None:
    """Append entry to log file."""
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(log_file, "a") as f:
        f.write(entry + "\n")


def format_usd(value: float) -> str:
    """Format USD value with commas."""
    return f"${value:,.0f}"


def format_labeled_wrapped(label: str, value: str, *, width: int = 84, hanging_indent: int = 2) -> str:
    """
    Format a labeled line with wrapping (no ellipsis).

    Example:
        Market: This is a long market question that wraps
          onto the next line.
    """
    if not value:
        return f"{label}: N/A"
    wrapped = textwrap.fill(
        str(value),
        width=width,
        subsequent_indent=" " * hanging_indent,
        break_long_words=False,
        break_on_hyphens=False,
    )
    lines = wrapped.splitlines()
    lines[0] = f"{label}: {lines[0]}"
    return "\n".join(lines)


def fetch_event_markets(event_slug: str) -> dict:
    """
    Fetch all markets for a UFC event using the Gamma API.
    
    Supports two modes:
    1. Event slug lookup (e.g., "ufc-jus3-pad-2026-01-24")
    2. Keyword search (e.g., "gaethje pimblett" or "ufc 311")
    
    Returns a dict with:
    - event_title: str
    - event_url: str  
    - markets: list of market dicts with token mappings
    """
    print(f"[INFO] Fetching markets for: {event_slug}")
    
    event_markets = []
    event_title = None
    event_actual_slug = event_slug
    
    # Try 1: Direct event slug lookup via /events endpoint
    # Ref: https://gamma-api.polymarket.com/events?slug=<slug>
    try:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={"slug": event_slug},
            timeout=30,
        )
        resp.raise_for_status()
        events_data = resp.json()
        
        if events_data and len(events_data) > 0:
            event = events_data[0]
            event_title = event.get("title", event_slug)
            event_actual_slug = event.get("slug", event_slug)
            event_markets = event.get("markets", [])
            print(f"[INFO] Found event: {event_title}")
    except Exception as e:
        print(f"[WARN] Events API error: {e}")
    
    # Try 2: Direct market slug lookup if event lookup failed
    if not event_markets:
        print(f"[INFO] Trying markets endpoint...")
        try:
            resp = requests.get(
                f"{GAMMA_API}/markets",
                params={"slug": event_slug},
                timeout=30,
            )
            resp.raise_for_status()
            markets_data = resp.json()
            
            if markets_data and len(markets_data) > 0:
                # This returns the main market, get associated markets from events
                main_market = markets_data[0]
                event_title = main_market.get("question", event_slug)
                event_actual_slug = main_market.get("slug", event_slug)
                event_markets = [main_market]
                
                # Also fetch related markets from the event
                events = main_market.get("events", [])
                if events:
                    event_slug_from_market = events[0].get("slug")
                    if event_slug_from_market:
                        resp2 = requests.get(
                            f"{GAMMA_API}/events",
                            params={"slug": event_slug_from_market},
                            timeout=30,
                        )
                        if resp2.ok:
                            events_data = resp2.json()
                            if events_data:
                                event_markets = events_data[0].get("markets", [])
                                event_title = events_data[0].get("title", event_title)
                                event_actual_slug = events_data[0].get("slug", event_actual_slug)
        except Exception as e:
            print(f"[WARN] Markets API error: {e}")
    
    # Try 3: Keyword search as fallback
    if not event_markets:
        print(f"[INFO] No exact match, trying keyword search...")
        try:
            resp = requests.get(
                f"{GAMMA_API}/markets",
                params={"closed": "false", "limit": 500},
                timeout=60,
            )
            resp.raise_for_status()
            all_markets = resp.json()
            
            keywords = event_slug.lower().replace("-", " ").split()
            
            for market in all_markets:
                question = market.get("question", "").lower()
                slug = market.get("slug", "").lower()
                searchable = f"{question} {slug}"
                
                if all(kw in searchable for kw in keywords):
                    event_markets.append(market)
                    if not event_title:
                        events = market.get("events") or []
                        if events:
                            event_title = events[0].get("title", event_slug)
                            event_actual_slug = events[0].get("slug", event_slug)
                        else:
                            event_title = market.get("question", event_slug)
                            event_actual_slug = market.get("slug", event_slug)
        except Exception as e:
            print(f"[ERROR] Search failed: {e}")
    
    if not event_markets:
        print(f"[ERROR] No markets found for: {event_slug}")
        print("[INFO] Try using fighter names as keywords (e.g., 'gaethje pimblett')")
        sys.exit(1)
    
    # Build token ID -> market info mapping
    token_map = {}  # token_id -> {market_title, outcome, price, slug, market_type}
    all_token_ids = []
    
    for market in event_markets:
        question = market.get("question", "")
        slug = market.get("slug", "")
        market_type = (
            market.get("sportsMarketType")
            or market.get("marketType")
            or market.get("type")
            or market.get("groupItemTitle")
            or market.get("title")
            or ""
        )
        
        # Parse outcomes and clob token IDs
        outcomes_raw = market.get("outcomes")
        tokens_raw = market.get("clobTokenIds")
        prices_raw = market.get("outcomePrices")
        
        # Handle string or list formats
        if isinstance(outcomes_raw, str):
            try:
                outcomes = json.loads(outcomes_raw)
            except:
                outcomes = [outcomes_raw]
        else:
            outcomes = outcomes_raw or []
            
        if isinstance(tokens_raw, str):
            try:
                tokens = json.loads(tokens_raw)
            except:
                tokens = [tokens_raw]
        else:
            tokens = tokens_raw or []
            
        if isinstance(prices_raw, str):
            try:
                prices = [float(p) for p in json.loads(prices_raw)]
            except:
                prices = []
        else:
            prices = [float(p) for p in (prices_raw or [])]
        
        # Map each token to its outcome
        for i, token_id in enumerate(tokens):
            if not token_id:
                continue
            outcome_name = outcomes[i] if i < len(outcomes) else f"Outcome {i}"
            price = prices[i] if i < len(prices) else None
            
            token_map[token_id] = {
                "market_title": question,
                "outcome": outcome_name,
                "price": price,
                "slug": slug,
                "market_type": market_type,
            }
            all_token_ids.append(token_id)
    
    print(f"[INFO] Found {len(event_markets)} markets with {len(all_token_ids)} tokens")
    
    return {
        "event_title": event_title,
        "event_slug": event_actual_slug,
        "event_url": f"https://polymarket.com/event/{event_actual_slug}",
        "markets": event_markets,
        "token_map": token_map,
        "token_ids": all_token_ids,
    }


def process_price_change(data: dict, token_map: dict, event_info: dict, 
                         threshold: float, log_file: str) -> None:
    """
    Process a price_change event and alert on large trades.
    
    Per https://docs.polymarket.com/developers/CLOB/websocket/market-channel:
    price_changes contain: asset_id, price, size, side, best_bid, best_ask
    """
    price_changes = data.get("price_changes", [])
    timestamp = datetime.now().isoformat()
    
    for change in price_changes:
        asset_id = change.get("asset_id")
        price = float(change.get("price", 0))
        size = float(change.get("size", 0))
        side = change.get("side", "")
        best_bid = change.get("best_bid", "")
        best_ask = change.get("best_ask", "")
        
        # Calculate USD value: size * price for a BUY
        usd_value = size * price
        
        # Get market info from token map
        market_info = token_map.get(asset_id, {})
        market_title = market_info.get("market_title", "Unknown Market")
        outcome = market_info.get("outcome", "Unknown")
        market_slug = market_info.get("slug", "") or ""
        market_type = market_info.get("market_type", "") or ""
        
        # Log all trades
        log_entry = (
            f"{timestamp} | {market_title} | {outcome} | {side} | "
            f"size={size:.0f} | price={price:.4f} | usd={usd_value:.2f}"
        )
        log_event(log_file, log_entry)
        
        # Only alert on BUY side to avoid duplicate notifications
        if side != "BUY":
            continue
        
        # Check threshold
        if usd_value >= threshold:
            potential_profit = size * (1 - price)

            # Build a more descriptive, non-truncating notification.
            event_title = event_info.get("event_title") or "UFC Event"
            event_url = event_info.get("event_url") or ""

            market_display_parts = []
            if market_type and market_type != market_title:
                market_display_parts.append(str(market_type))
            if market_title:
                market_display_parts.append(str(market_title))
            market_display = " — ".join([p for p in market_display_parts if p])

            details_lines = [
                "Poly Sports Bot",
                "🥊 UFC WHALE ALERT",
                "",
                f"Outcome: {outcome} (BUY)",
                f"Wager: {format_usd(usd_value)} @ {price:.0%}  |  Shares: {size:,.0f}",
                f"Est. profit: {format_usd(potential_profit)}",
                "",
                format_labeled_wrapped("Event", event_title),
                format_labeled_wrapped("Market", market_display),
            ]
            if market_slug:
                details_lines.append(format_labeled_wrapped("Market slug", market_slug))
            if best_bid or best_ask:
                bid_ask = f"{best_bid or 'N/A'} / {best_ask or 'N/A'}"
                details_lines.append(f"Best bid/ask: {bid_ask}")

            # Put link(s) at the bottom (as requested).
            if event_url:
                details_lines.extend(["", f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}", event_url])

            msg = "\n".join(details_lines)
            
            print(f"\n{'='*60}")
            print(f"[ALERT] {timestamp}")
            print(f"Market: {market_title}")
            print(f"Outcome: {outcome}")
            print(f"Side: {side} | Size: {size:,.0f} | Price: {price:.4f}")
            print(f"USD Value: {format_usd(usd_value)}")
            print(f"Potential Profit: {format_usd(potential_profit)}")
            print(f"{'='*60}\n")
            
            send_pushover(msg, event_info.get("event_url"))


def run_monitor(event_slug: str, threshold: float):
    """Main monitoring loop with reconnection logic."""
    
    # Fetch event markets
    event_info = fetch_event_markets(event_slug)
    token_map = event_info["token_map"]
    token_ids = event_info["token_ids"]
    
    if not token_ids:
        print("[ERROR] No token IDs found to monitor")
        sys.exit(1)
    
    # Setup logging
    log_file = os.path.join(LOG_DIR, f"ufc_{event_slug}.log")
    
    print()
    print(f"[INFO] Starting UFC Whale Monitor")
    print(f"[INFO] Event: {event_info['event_title']}")
    print(f"[INFO] URL: {event_info['event_url']}")
    print(f"[INFO] Threshold: {format_usd(threshold)}")
    print(f"[INFO] Monitoring {len(token_ids)} tokens across {len(event_info['markets'])} markets")
    print(f"[INFO] Log file: {log_file}")
    print()
    
    # Print market summary
    print("[INFO] Markets being monitored:")
    seen_markets = set()
    for token_id, info in token_map.items():
        market_title = info["market_title"]
        if market_title not in seen_markets:
            seen_markets.add(market_title)
            print(f"  - {market_title}")
    print()
    
    while True:
        try:
            ws = create_connection(WS_URL)
            print(f"[INFO] Connected to WebSocket: {WS_URL}")
            
            # Subscribe to market channel for all token IDs
            # Ref: https://docs.polymarket.com/developers/CLOB/websocket/market-channel
            subscribe_msg = {
                "type": "market",
                "assets_ids": token_ids
            }
            ws.send(json.dumps(subscribe_msg))
            print(f"[INFO] Subscribed to {len(token_ids)} asset IDs")
            print("[INFO] Listening for trades...\n")
            
            while True:
                try:
                    message = ws.recv()
                    raw_data = json.loads(message)
                    
                    # Handle list response (initial book snapshots)
                    if isinstance(raw_data, list):
                        for item in raw_data:
                            event_type = item.get("event_type")
                            if event_type == "book":
                                asset_id = item.get("asset_id", "")[:20]
                                last_price = item.get("last_trade_price", "N/A")
                                print(f"[INFO] Book snapshot: {asset_id}... last_price={last_price}")
                        continue
                    
                    data = raw_data
                    event_type = data.get("event_type")
                    
                    if event_type == "book":
                        asset_id = data.get("asset_id", "")[:20]
                        last_price = data.get("last_trade_price", "N/A")
                        print(f"[INFO] Book update: {asset_id}... last_price={last_price}")
                    
                    elif event_type == "price_change":
                        process_price_change(data, token_map, event_info, threshold, log_file)
                    
                except WebSocketConnectionClosedException:
                    print("[WARN] WebSocket connection closed, reconnecting...")
                    break
                    
        except Exception as e:
            print(f"[ERROR] WebSocket error: {e}")
            
        print("[INFO] Reconnecting in 5 seconds...")
        time.sleep(5)


def main():
    parser = argparse.ArgumentParser(
        description="Monitor UFC event markets for large wagers"
    )
    parser.add_argument(
        "event_slug",
        help="Polymarket event slug (e.g., ufc-jus3-pad-2026-01-24)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_USD_THRESHOLD,
        help=f"USD threshold for whale alerts (default: {DEFAULT_USD_THRESHOLD})"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("UFC Large Wager Monitor")
    print("=" * 60)
    print()
    print("References:")
    print("- Gamma API: https://docs.polymarket.com/api-reference/core/get-market")
    print("- WebSocket: https://docs.polymarket.com/developers/CLOB/websocket/market-channel")
    print()
    
    run_monitor(args.event_slug, args.threshold)


if __name__ == "__main__":
    main()
