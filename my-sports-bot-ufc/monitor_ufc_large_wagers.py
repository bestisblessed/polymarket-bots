#!/usr/bin/env python3
"""
UFC Large Wager Monitor via Polymarket CLOB WebSocket

Monitors all markets for a UFC event and sends Pushover notifications
when large wagers are detected.

Usage:
    python monitor_ufc_large_wagers.py [all|<event_slug>]

Example:
    python monitor_ufc_large_wagers.py all
    python monitor_ufc_large_wagers.py ufc-jus3-pad-2026-01-24

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
from typing import Optional
import re

from json import JSONDecodeError

import requests
from dotenv import load_dotenv
from requests_oauthlib import OAuth1
import websocket

load_dotenv()

# === API Endpoints ===
GAMMA_API = "https://gamma-api.polymarket.com"
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json"
PUSHOVER_TITLE = "UFC Whale Monitor 🥊"
X_POST_ENDPOINT = "https://api.x.com/2/tweets"

# === Default Settings ===
LOG_DIR = "logs"

# === Health Check Settings ===
HEALTHCHECK_URL = "https://hc-ping.com/fa7ea775-465a-4901-8b36-ed05b7d787ce"
#HEALTHCHECK_INTERVAL = 300  # 5 minutes
HEALTHCHECK_INTERVAL = 900

# === WebSocket Keepalive Settings ===
# Protocol-level ping frames detect dead connections (half-open TCP)
WS_PING_INTERVAL = 30   # seconds between ping frames
WS_PING_TIMEOUT = 10    # seconds to wait for pong before declaring dead

# Health check stale threshold: if no WS message received in this many seconds,
# send a /fail ping to healthchecks.io instead of a success ping
HEALTHCHECK_STALE_THRESHOLD = 300  # 5 minutes


def send_pushover(message: str, url: Optional[str] = None, title: Optional[str] = None) -> None:
    """Send a Pushover notification."""
    token = os.environ.get("PUSHOVER_API_TOKEN")
    user = os.environ.get("PUSHOVER_GROUP_KEY")
    if not token or not user:
        print("[WARN] Pushover credentials not found in env, skipping notification")
        return
    data = {"token": token, "user": user, "message": message, "html": 1}
    data["title"] = title or PUSHOVER_TITLE
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


def clamp_tweet_text(text: str) -> str:
    """Keep the post inside X's 280 character limit."""
    if len(text) <= 280:
        return text
    return text[:277].rstrip() + "..."


def build_x_alert_tweet(
    event_title: str,
    market_display: str,
    outcome: str,
    price: float,
    usd_value: float,
    potential_profit: float,
    shares: float,
) -> str:
    """Build the short public X alert text."""
    return clamp_tweet_text(
        "\n".join(
            [
                "🚨🐳  UFC Whale Alert  🚨🐳",
                "",
                f"Event: {event_title}",
                f"Market: {market_display}",
                f"Bet: {outcome} @ {price:.0%}",
                f"Size: {format_usd(usd_value)} to win {format_usd(potential_profit)} ({shares:,.2f} Shares)",
            ]
        )
    )


def send_x_tweet(text: str) -> None:
    """Post a text-only X tweet with OAuth 1.0a user context."""
    required = [
        "X_API_KEY",
        "X_API_SECRET",
        "X_ACCESS_TOKEN",
        "X_ACCESS_TOKEN_SECRET",
    ]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print(f"[WARN] X credentials missing ({', '.join(missing)}), skipping tweet")
        return

    auth = OAuth1(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_TOKEN_SECRET"],
    )

    try:
        resp = requests.post(
            X_POST_ENDPOINT,
            auth=auth,
            json={"text": clamp_tweet_text(text)},
            timeout=30,
        )
        if resp.ok:
            try:
                tweet_id = resp.json().get("data", {}).get("id")
            except ValueError:
                tweet_id = None
            if tweet_id:
                print(f"[INFO] X tweet sent: {tweet_id}")
            else:
                print("[INFO] X tweet sent")
        else:
            print(f"[WARN] X tweet failed: {resp.status_code} {resp.text[:300]}")
    except Exception as e:
        print(f"[ERROR] X tweet error: {e}")


def log_event(log_file: str, entry: str) -> None:
    """Append entry to log file."""
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(log_file, "a") as f:
        f.write(entry + "\n")


def send_health_ping(url: str) -> None:
    """Send HTTP ping to healthcheck service."""
    try:
        resp = requests.get(url, timeout=10)
        if resp.ok:
            print(f"[INFO] Health check ping sent: {resp.status_code}")
        else:
            print(f"[WARN] Health check ping failed: {resp.status_code}")
    except Exception as e:
        print(f"[WARN] Health check ping error (non-fatal): {e}")


def health_check_worker(
    url: str,
    interval: int,
    stop_event: threading.Event,
    last_message_time: list,
) -> None:
    """
    Background worker that sends periodic health check pings.

    Only sends a success ping if the WebSocket has received a message recently
    (within HEALTHCHECK_STALE_THRESHOLD seconds). Otherwise sends a /fail ping
    so healthchecks.io triggers an alert.
    """
    print(f"[INFO] Health check worker started (interval: {interval}s)")

    # Send initial ping on startup
    send_health_ping(url)

    while not stop_event.is_set():
        for _ in range(interval):
            if stop_event.is_set():
                break
            time.sleep(1)

        if not stop_event.is_set():
            elapsed = time.time() - last_message_time[0]
            if elapsed > HEALTHCHECK_STALE_THRESHOLD:
                print(f"[WARN] No WS message for {elapsed:.0f}s — sending /fail health ping")
                send_health_ping(f"{url}/fail")
            else:
                send_health_ping(url)

    print("[INFO] Health check worker stopped")



def heartbeat_worker(
    interval: int,
    stop_event: threading.Event,
    last_message_time: list,
    token_count: int,
) -> None:
    """Print a heartbeat every `interval` seconds so you can tell it's alive during quiet markets."""
    while not stop_event.is_set():
        for _ in range(interval):
            if stop_event.is_set():
                break
            time.sleep(1)

        if not stop_event.is_set():
            elapsed = time.time() - last_message_time[0]
            if elapsed < 60:
                ago = f"{elapsed:.0f}s ago"
            else:
                ago = f"{elapsed / 60:.0f}m ago"
            print(f"[INFO] Heartbeat: alive, last WS msg {ago}, {token_count} tokens monitored")


def format_usd(value: float, *, decimals: int = 2) -> str:
    """Format USD value with commas and fixed decimals."""
    return f"${value:,.{decimals}f}"


def parse_threshold_from_env() -> float:
    """Read and parse THRESHOLD from environment (.env via dotenv)."""
    raw = os.environ.get("THRESHOLD")
    if raw is None or str(raw).strip() == "":
        raise ValueError("Missing THRESHOLD in environment")
    cleaned = str(raw).strip().replace("$", "").replace(",", "")
    return float(cleaned)


def clean_event_title(title: Optional[str]) -> str:
    cleaned = (title or "").strip()
    if "(" in cleaned:
        cleaned = cleaned[:cleaned.rfind("(")].strip()
    # Normalize UFC prefix titles: "UFC ...: X" -> "UFC ... - X"
    cleaned = re.sub(r"^(UFC[^:]{0,80})\s*:\s*", r"\1 - ", cleaned)
    return cleaned


def derive_fight_label(event_title: Optional[str], markets: list) -> str:
    """Best-effort fight label like 'Volkanovski vs. Lopes'."""
    for m in markets or []:
        if (m.get("sportsMarketType") or "") == "moneyline":
            group = (m.get("groupItemTitle") or "").strip()
            if group:
                return group

    cleaned = clean_event_title(event_title)
    if ": " in cleaned:
        cleaned = cleaned.split(": ", 1)[1].strip()
    elif cleaned.startswith("UFC") and " - " in cleaned:
        cleaned = cleaned.split(" - ", 1)[1].strip()
    return cleaned or "UFC Fight"


def build_token_map_for_event(*, event_slug: str, event_title: Optional[str], markets: list) -> dict:
    """Build token map + token IDs for a single event."""
    event_url = f"https://polymarket.com/event/{event_slug}"
    event_title_clean = clean_event_title(event_title)
    fight_label = derive_fight_label(event_title, markets)

    token_map = {}
    token_ids = []

    for market in markets or []:
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

        group_item_title = (market.get("groupItemTitle") or "").strip()
        sports_market_type = (market.get("sportsMarketType") or "").strip()

        outcomes_raw = market.get("outcomes")
        tokens_raw = market.get("clobTokenIds")
        prices_raw = market.get("outcomePrices")

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

        if isinstance(prices_raw, str):
            try:
                prices = [float(p) for p in json.loads(prices_raw)]
            except Exception:
                prices = []
        else:
            prices = [float(p) for p in (prices_raw or [])]

        for i, token_id in enumerate(tokens):
            if not token_id:
                continue
            outcome_name = outcomes[i] if i < len(outcomes) else f"Outcome {i}"
            price = prices[i] if i < len(prices) else None

            token_map[token_id] = {
                "event_slug": event_slug,
                "event_title": event_title_clean,
                "event_url": event_url,
                "fight_label": fight_label,
                "market_title": question,
                "outcome": outcome_name,
                "price": price,
                "slug": slug,
                "market_type": market_type,
                "group_item_title": group_item_title,
                "sports_market_type": sports_market_type,
            }
            token_ids.append(token_id)

    return {
        "event_slug": event_slug,
        "event_title": event_title_clean,
        "event_url": event_url,
        "fight_label": fight_label,
        "markets": markets or [],
        "token_map": token_map,
        "token_ids": token_ids,
    }


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
    - fight_label: str
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

    state = build_token_map_for_event(
        event_slug=event_actual_slug,
        event_title=event_title,
        markets=event_markets,
    )

    print(f"[INFO] Found {len(event_markets)} markets with {len(state['token_ids'])} tokens")
    return state


def fetch_ufc_fight_events(*, limit: int = 200) -> list:
    """Fetch all active, open UFC fight events (moneyline present)."""
    offset = 0
    fights = []

    while True:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={
                "tag_slug": "ufc",
                "active": "true",
                "closed": "false",
                "archived": "false",
                "limit": limit,
                "offset": offset,
            },
            timeout=60,
        )
        resp.raise_for_status()
        events = resp.json() or []
        if not events:
            break

        for ev in events:
            markets = ev.get("markets") or []
            if not markets:
                continue
            has_moneyline = any((m.get("sportsMarketType") or "") == "moneyline" for m in markets)
            if not has_moneyline:
                continue
            slug = ev.get("slug")
            if not slug:
                continue
            fights.append(ev)

        offset += len(events)

    return fights


def process_last_trade_price(data: dict, token_map: dict, threshold: float) -> None:
    """
    Process a last_trade_price event and alert on large executed trades.

    Per https://docs.polymarket.com/developers/CLOB/websocket/market-channel:
    last_trade_price includes asset_id, price, size, side, and timestamp.
    """
    asset_id = data.get("asset_id")
    price = float(data.get("price", 0))
    size = float(data.get("size", 0))
    side = data.get("side", "")
    timestamp_ms = data.get("timestamp")

    if timestamp_ms:
        timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000).isoformat()
    else:
        timestamp = datetime.now().isoformat()

    usd_value = size * price

    market_info = token_map.get(asset_id, {})
    market_title = market_info.get("market_title", "Unknown Market")
    outcome = market_info.get("outcome", "Unknown")
    group_item_title = market_info.get("group_item_title", "")
    sports_market_type = market_info.get("sports_market_type", "")

    event_slug = market_info.get("event_slug", "unknown")
    event_title = market_info.get("event_title") or "UFC Event"
    event_url = market_info.get("event_url") or ""
    # Fight label is already in the Event line; Market line should be the specific market only.

    log_file = os.path.join(LOG_DIR, f"ufc_{event_slug}.log")

    log_entry = (
        f"{timestamp} | {market_title} | {outcome} | {side} | "
        f"size={size:.4f} | price={price:.4f} | usd={usd_value:.2f}"
    )
    log_event(log_file, log_entry)

    if side != "BUY":
        return

    if usd_value >= threshold:
        potential_profit = size * (1 - price)

        if sports_market_type == "moneyline":
            market_display = "Moneyline"
        elif group_item_title:
            market_display = group_item_title
        else:
            market_display = market_title

        msg_lines = [
            f"Event: {event_title}",
            format_labeled_wrapped("Market", market_display, width=84, hanging_indent=2),
            f"Bet: {outcome} @ {price:.0%}",
            f"Size: {format_usd(usd_value)} to win {format_usd(potential_profit)} ({size:,.2f} Shares)",
        ]

        msg = "\n".join(msg_lines)

        print(f"\n{'='*60}")
        print(f"[ALERT] {timestamp}")
        print(f"Market: {market_display}")
        print(f"Outcome: {outcome}")
        print(f"Side: {side} | Size: {size:,.4f} | Price: {price:.4f}")
        print(f"USD Value: {format_usd(usd_value)}")
        print(f"Potential Profit: {format_usd(potential_profit)}")
        print(f"{'='*60}\n")

        send_pushover(msg, event_url)
        if price >= 0.995:
            print("[INFO] X tweet skipped: bet price is already 100%")
            return
        send_x_tweet(
            build_x_alert_tweet(
                event_title,
                market_display,
                outcome,
                price,
                usd_value,
                potential_profit,
                size,
            )
        )


def run_monitor(target: str, threshold: float):
    """Main monitoring loop with reconnection logic."""

    if (target or "").lower() == "all":
        print("[INFO] Fetching all active UFC fights...")
        events = fetch_ufc_fight_events()
        if not events:
            print("[ERROR] No UFC fight events found")
            sys.exit(1)

        token_map = {}
        token_ids = []
        total_markets = 0

        for ev in events:
            slug = ev.get("slug")
            title = ev.get("title")
            markets = ev.get("markets") or []
            state = build_token_map_for_event(event_slug=slug, event_title=title, markets=markets)
            total_markets += len(state.get("markets") or [])
            for tid, info in state["token_map"].items():
                token_map[tid] = info
            token_ids.extend(state["token_ids"])

        # Deduplicate, keep stable-ish order
        seen = set()
        token_ids = [tid for tid in token_ids if not (tid in seen or seen.add(tid))]

        label = f"ALL UFC fights ({len(events)} fights)"
        log_hint = f"{LOG_DIR}/ufc_<event_slug>.log"

        print()
        print(f"[INFO] Starting UFC Whale Monitor")
        print(f"[INFO] Target: {label}")
        print(f"[INFO] Threshold: {format_usd(threshold)}")
        print(f"[INFO] Monitoring {len(token_ids)} tokens across {total_markets} markets")
        print(f"[INFO] Log files: {log_hint}")
        print()
    else:
        event_info = fetch_event_markets(target)
        token_map = event_info["token_map"]
        token_ids = event_info["token_ids"]

    if not token_ids:
        print("[ERROR] No token IDs found to monitor")
        sys.exit(1)

    # Print startup info for single-event mode
    if (target or "").lower() != "all":
        log_file = os.path.join(LOG_DIR, f"ufc_{event_info['event_slug']}.log")

        print()
        print(f"[INFO] Starting UFC Whale Monitor")
        print(f"[INFO] Event: {event_info['event_title']}")
        print(f"[INFO] URL: {event_info['event_url']}")
        print(f"[INFO] Threshold: {format_usd(threshold)}")
        print(f"[INFO] Monitoring {len(token_ids)} tokens across {len(event_info['markets'])} markets")
        print(f"[INFO] Log file: {log_file}")
        print()

        print("[INFO] Markets being monitored:")
        seen_markets = set()
        for _, info in token_map.items():
            market_title = info["market_title"]
            if market_title not in seen_markets:
                seen_markets.add(market_title)
                print(f"  - {market_title}")
        print()

    # Shared state for health check and heartbeat
    last_message_time = [time.time()]
    non_json_count = [0]

    def _subscribe_assets(ws_conn, asset_ids, *, chunk_size: int = 500) -> None:
        for i in range(0, len(asset_ids), chunk_size):
            chunk = asset_ids[i : i + chunk_size]
            ws_conn.send(json.dumps({"type": "market", "assets_ids": chunk}))
        print(f"[INFO] Subscribed to {len(asset_ids)} asset IDs")

    # === WebSocketApp callbacks ===

    def on_open(wsapp):
        print(f"[INFO] Connected to WebSocket: {WS_URL}")
        _subscribe_assets(wsapp, token_ids)
        print("[INFO] Listening for trades...\n")

    def on_message(wsapp, message):
        last_message_time[0] = time.time()

        if message is None:
            return

        if isinstance(message, bytes):
            try:
                message = message.decode("utf-8")
            except Exception:
                non_json_count[0] += 1
                if non_json_count[0] <= 3 or non_json_count[0] % 100 == 0:
                    print("[WARN] Non-UTF8 WS message ignored")
                return

        message = message.strip()
        if not message or message.upper() in {"PING", "PONG"}:
            return

        try:
            raw_data = json.loads(message)
        except JSONDecodeError:
            non_json_count[0] += 1
            if non_json_count[0] <= 3 or non_json_count[0] % 100 == 0:
                preview = message[:120]
                print(f"[WARN] Non-JSON WS message ignored: {preview!r}")
            return

        # Handle list response (initial book snapshots)
        if isinstance(raw_data, list):
            for item in raw_data:
                event_type = item.get("event_type")
                if event_type == "book":
                    asset_id = item.get("asset_id", "")[:20]
                    last_price = item.get("last_trade_price", "N/A")
                    print(f"[INFO] Book snapshot: {asset_id}... last_price={last_price}")
            return

        data = raw_data
        event_type = data.get("event_type")

        if event_type == "book":
            asset_id = data.get("asset_id", "")[:20]
            last_price = data.get("last_trade_price", "N/A")
            print(f"[INFO] Book update: {asset_id}... last_price={last_price}")

        elif event_type == "last_trade_price":
            process_last_trade_price(data, token_map, threshold)

    def on_error(wsapp, error):
        print(f"[ERROR] WebSocket error: {error}")

    def on_close(wsapp, close_status_code, close_msg):
        print(f"[WARN] WebSocket closed (code={close_status_code}, msg={close_msg})")

    def on_ping(wsapp, message):
        pass  # Library auto-sends pong

    def on_pong(wsapp, message):
        pass  # Confirms connection is alive

    # === START HEALTH CHECK THREAD ===
    health_check_thread = None
    stop_health_check = threading.Event()

    if HEALTHCHECK_URL:
        print(f"[INFO] Starting health check pings to: {HEALTHCHECK_URL}")
        print(f"[INFO] Health check interval: {HEALTHCHECK_INTERVAL}s")
        print(f"[INFO] Stale threshold: {HEALTHCHECK_STALE_THRESHOLD}s (sends /fail if no WS data)")
        health_check_thread = threading.Thread(
            target=health_check_worker,
            args=(HEALTHCHECK_URL, HEALTHCHECK_INTERVAL, stop_health_check, last_message_time),
            daemon=True,
        )
        health_check_thread.start()
    else:
        print("[INFO] Health check disabled (HEALTHCHECK_URL not set)")

    # === START HEARTBEAT THREAD ===
    stop_heartbeat = threading.Event()
    hb_thread = threading.Thread(
        target=heartbeat_worker,
        args=(300, stop_heartbeat, last_message_time, len(token_ids)),
        daemon=True,
    )
    hb_thread.start()

    print(f"[INFO] WebSocket ping interval: {WS_PING_INTERVAL}s (protocol-level)")
    print(f"[INFO] WebSocket ping timeout: {WS_PING_TIMEOUT}s")
    print(f"[INFO] Heartbeat interval: 300s")
    print(f"[INFO] Auto-reconnect: 5s delay")
    print()

    # === RUN WebSocketApp with auto-reconnect and protocol-level pings ===
    wsapp = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_ping=on_ping,
        on_pong=on_pong,
    )

    try:
        while True:
            wsapp.run_forever(
                ping_interval=WS_PING_INTERVAL,
                ping_timeout=WS_PING_TIMEOUT,
            )
            print("[INFO] Reconnecting in 5 seconds...")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down gracefully...")
    finally:
        stop_heartbeat.set()
        if health_check_thread:
            stop_health_check.set()
            health_check_thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(
        description="Monitor UFC event markets for large wagers"
    )
    parser.add_argument(
        "event_slug",
        nargs="?",
        default="all",
        help="Event slug (e.g., ufc-jus3-pad-2026-01-24) or 'all'"
    )
    
    args = parser.parse_args()

    try:
        threshold = parse_threshold_from_env()
    except Exception as e:
        print(f"[ERROR] Invalid or missing THRESHOLD in .env/env: {e}")
        print("[INFO] Set THRESHOLD in my-sports-bot-ufc/.env, e.g. THRESHOLD=1000")
        sys.exit(1)
    
    print("=" * 60)
    print("UFC Large Wager Monitor")
    print("=" * 60)
    print()
    print("References:")
    print("- Gamma API: https://docs.polymarket.com/api-reference/core/get-market")
    print("- WebSocket: https://docs.polymarket.com/developers/CLOB/websocket/market-channel")
    print()
    
    run_monitor(args.event_slug, threshold)


if __name__ == "__main__":
    main()
