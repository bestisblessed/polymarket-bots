#!/usr/bin/env python3
"""
UFC Open Order Monitor via Polymarket CLOB WebSocket

Monitors order book updates for a UFC event and sends Pushover notifications
when large open orders are detected.

Usage:
    python monitor_ufc_open_orders.py <event_slug> [--threshold <usd>]

Example:
    python monitor_ufc_open_orders.py ufc-jus3-pad-2026-01-24 --threshold 5000

References:
- Gamma API (markets): https://docs.polymarket.com/api-reference/core/get-market
- WebSocket Overview: https://docs.polymarket.com/developers/CLOB/websocket/wss-overview
- Market Channel: https://docs.polymarket.com/developers/CLOB/websocket/market-channel
"""

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime
import textwrap

import requests
from dotenv import load_dotenv
from websocket import WebSocketConnectionClosedException, create_connection

load_dotenv()

# === API Endpoints ===
GAMMA_API = "https://gamma-api.polymarket.com"
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json"

# === Default Settings ===
DEFAULT_USD_THRESHOLD = 5000.0
STATE_PATH = os.path.join("data", "ufc_open_orders_state.json")

state_lock = threading.Lock()
seen_orders = set()


def ensure_data_dir() -> None:
    os.makedirs("data", exist_ok=True)


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


def load_state() -> None:
    """Load previously seen order IDs from disk."""
    if not os.path.exists(STATE_PATH):
        return
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        with state_lock:
            seen_orders.update(payload.get("seen_orders", []))
        print(f"[INFO] Loaded {len(seen_orders)} previously seen orders")
    except Exception as e:
        print(f"[WARN] Failed to load state: {e}")


def save_state() -> None:
    """Persist seen order IDs to disk."""
    ensure_data_dir()
    with state_lock:
        payload = {"seen_orders": sorted(seen_orders)}
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        print(f"[WARN] Failed to save state: {e}")


def generate_order_id(asset_id: str, side: str, price: float, size: float) -> str:
    """Generate a unique ID for an aggregated book level."""
    return f"{asset_id}:{side}:{price}:{size}"


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
        print("[INFO] Trying markets endpoint...")
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
        print("[INFO] No exact match, trying keyword search...")
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
    token_map = {}  # token_id -> {market_title, outcome, slug, market_type}
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

        # Handle string or list formats
        if isinstance(outcomes_raw, str):
            try:
                outcomes = json.loads(outcomes_raw)
            except Exception:
                outcomes = [outcomes_raw]
        else:
            outcomes = outcomes_raw or []

        if isinstance(tokens_raw, str):
            try:
                tokens = json.loads(tokens_raw)
            except Exception:
                tokens = [tokens_raw]
        else:
            tokens = tokens_raw or []

        # Map each token to its outcome
        for i, token_id in enumerate(tokens):
            if not token_id:
                continue
            outcome_name = outcomes[i] if i < len(outcomes) else f"Outcome {i}"

            token_map[token_id] = {
                "market_title": question,
                "outcome": outcome_name,
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


def parse_order_levels(raw_levels) -> list:
    """Parse order levels from book payloads."""
    levels = raw_levels or []
    parsed = []
    for level in levels:
        try:
            price = float(level.get("price", 0))
            size = float(level.get("size", 0))
        except (TypeError, ValueError):
            continue
        parsed.append((price, size))
    return parsed


def get_best_prices(bids: list, asks: list) -> tuple:
    """Return best bid and ask from parsed levels."""
    best_bid = max((price for price, _ in bids), default=None)
    best_ask = min((price for price, _ in asks), default=None)
    return best_bid, best_ask


def build_market_display(market_info: dict) -> str:
    market_title = market_info.get("market_title", "")
    market_type = market_info.get("market_type", "")
    parts = []
    if market_type and market_type != market_title:
        parts.append(str(market_type))
    if market_title:
        parts.append(str(market_title))
    return " — ".join([p for p in parts if p])


def alert_on_order(
    asset_id: str,
    side: str,
    price: float,
    size: float,
    best_bid: float,
    best_ask: float,
    token_map: dict,
    event_info: dict,
    threshold: float,
) -> None:
    order_value = price * size
    if order_value < threshold:
        return

    order_id = generate_order_id(asset_id, side, price, size)
    with state_lock:
        if order_id in seen_orders:
            return
        seen_orders.add(order_id)
    save_state()

    market_info = token_map.get(asset_id, {})
    outcome = market_info.get("outcome", "Unknown")
    market_display = build_market_display(market_info)

    best_bid_display = f"{best_bid:.2f}" if best_bid is not None else "N/A"
    best_ask_display = f"{best_ask:.2f}" if best_ask is not None else "N/A"

    info_block = [
        "🥊 UFC Open Orders",
        "",
        format_labeled_wrapped("Event", event_info.get("event_title") or "UFC Event"),
        format_labeled_wrapped("Market", market_display),
        f"Best bid/ask: {best_bid_display} / {best_ask_display}",
    ]

    order_block = [
        "",
        f"Outcome: {outcome} ({side})",
        f"Order: {format_usd(order_value)} @ {price:.0%}  |  Shares: {size:,.0f}",
    ]

    link_block = []
    if event_info.get("event_url"):
        link_block = ["", event_info["event_url"]]

    msg = "\n".join(info_block + order_block + link_block)

    timestamp = datetime.now().isoformat()
    print(f"\n{'='*60}")
    print(f"[ALERT] {timestamp}")
    print(f"Market: {market_info.get('market_title', 'Unknown Market')}")
    print(f"Outcome: {outcome}")
    print(f"Side: {side} | Shares: {size:,.0f} | Price: {price:.4f}")
    print(f"Order Value: {format_usd(order_value)}")
    print(f"Best bid/ask: {best_bid_display} / {best_ask_display}")
    print(f"{'='*60}\n")

    send_pushover(msg, event_info.get("event_url"), title="UFC Open Order Alert")


def handle_book_event(data: dict, token_map: dict, event_info: dict, threshold: float) -> None:
    """
    Handle order book updates and alert on large pending orders.

    Per https://docs.polymarket.com/developers/CLOB/websocket/market-channel:
    book messages contain bids/asks (aggregate price levels).
    """
    asset_id = data.get("asset_id")
    if not asset_id:
        return

    raw_bids = data.get("bids", data.get("buys", []))
    raw_asks = data.get("asks", data.get("sells", []))

    bids = parse_order_levels(raw_bids)
    asks = parse_order_levels(raw_asks)

    best_bid, best_ask = get_best_prices(bids, asks)

    for price, size in bids:
        alert_on_order(
            asset_id,
            "BUY",
            price,
            size,
            best_bid,
            best_ask,
            token_map,
            event_info,
            threshold,
        )

    for price, size in asks:
        alert_on_order(
            asset_id,
            "SELL",
            price,
            size,
            best_bid,
            best_ask,
            token_map,
            event_info,
            threshold,
        )


def run_monitor(event_slug: str, threshold: float) -> None:
    """Main monitoring loop with reconnection logic."""
    event_info = fetch_event_markets(event_slug)
    token_map = event_info["token_map"]
    token_ids = event_info["token_ids"]

    if not token_ids:
        print("[ERROR] No token IDs found to monitor")
        sys.exit(1)

    load_state()

    print()
    print("[INFO] Starting UFC Open Order Monitor")
    print(f"[INFO] Event: {event_info['event_title']}")
    print(f"[INFO] URL: {event_info['event_url']}")
    print(f"[INFO] Threshold: {format_usd(threshold)}")
    print(f"[INFO] Monitoring {len(token_ids)} tokens across {len(event_info['markets'])} markets")
    print()

    try:
        while True:
            try:
                ws = create_connection(WS_URL)
                print(f"[INFO] Connected to WebSocket: {WS_URL}")

                subscribe_msg = {
                    "type": "market",
                    "assets_ids": token_ids,
                }
                ws.send(json.dumps(subscribe_msg))
                print(f"[INFO] Subscribed to {len(token_ids)} asset IDs")
                print("[INFO] Listening for order book updates...\n")

                while True:
                    try:
                        message = ws.recv()
                        raw_data = json.loads(message)

                        if isinstance(raw_data, list):
                            for item in raw_data:
                                if item.get("event_type") == "book":
                                    handle_book_event(item, token_map, event_info, threshold)
                            continue

                        if raw_data.get("event_type") == "book":
                            handle_book_event(raw_data, token_map, event_info, threshold)

                    except WebSocketConnectionClosedException:
                        print("[WARN] WebSocket connection closed, reconnecting...")
                        break

            except Exception as e:
                print(f"[ERROR] WebSocket error: {e}")

            print("[INFO] Reconnecting in 5 seconds...")
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n[INFO] Shutting down gracefully...")
        sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitor UFC event markets for large open orders"
    )
    parser.add_argument(
        "event_slug",
        help="Polymarket event slug (e.g., ufc-jus3-pad-2026-01-24)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_USD_THRESHOLD,
        help=f"USD threshold for open order alerts (default: {DEFAULT_USD_THRESHOLD})",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("UFC Open Order Monitor")
    print("=" * 60)
    print()
    print("References:")
    print("- Gamma API: https://docs.polymarket.com/api-reference/core/get-market")
    print("- WebSocket: https://docs.polymarket.com/developers/CLOB/websocket/market-channel")
    print()

    run_monitor(args.event_slug, args.threshold)


if __name__ == "__main__":
    main()
