#!/usr/bin/env python3
"""
NFL Large Wager Monitor via Polymarket CLOB WebSocket

Monitors the Rams vs Panthers moneyline market for large wagers and sends
Pushover notifications when trades exceed the configured threshold.

References:
- WebSocket Overview: https://docs.polymarket.com/developers/CLOB/websocket/wss-overview
- WebSocket Quickstart: https://docs.polymarket.com/quickstart/websocket/WSS-Quickstart
- Market Channel: https://docs.polymarket.com/developers/CLOB/websocket/market-channel

The market channel subscribes to asset IDs and receives:
- 'book' events: Full orderbook snapshots with bids/asks
- 'price_change' events: Real-time trades with size, price, and side

Event URL: https://polymarket.com/event/nfl-la-car-2026-01-10
"""

import json
import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from websocket import create_connection, WebSocketConnectionClosedException

load_dotenv()

# === Market Configuration ===
# Rams vs Panthers Moneyline - fetched from gamma-api.polymarket.com
# clobTokenIds: ["78771016858683590931968399206043033368231163700315025308842883779104149970413", "915627592033002568512857939649312443434425908803980109605482558466978444816"]
RAMS_TOKEN_ID = "78771016858683590931968399206043033368231163700315025308842883779104149970413"
PANTHERS_TOKEN_ID = "915627592033002568512857939649312443434425908803980109605482558466978444816"

TOKEN_NAMES = {
    RAMS_TOKEN_ID: "Rams",
    PANTHERS_TOKEN_ID: "Panthers",
}

# All token IDs to subscribe to
ASSET_IDS = [RAMS_TOKEN_ID, PANTHERS_TOKEN_ID]

# WebSocket endpoint per https://docs.polymarket.com/developers/CLOB/websocket/wss-overview
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

# === Notification Thresholds ===
# Minimum USD value to trigger a notification
USD_THRESHOLD = 5000.0

# Pushover settings
PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json"

# Log file
LOG_FILE = "logs/nfl_large_wagers.log"


def send_pushover(message: str, url: str = None) -> None:
    """Send a Pushover notification."""
    token = os.environ.get("PUSHOVER_API_TOKEN")
    user = os.environ.get("PUSHOVER_GROUP_KEY")
    if not token or not user:
        print("[WARN] Pushover credentials not found in env, skipping notification")
        return
    data = {"token": token, "user": user, "message": message, "html": 1}
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


def log_event(entry: str) -> None:
    """Append entry to log file."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(entry + "\n")


def format_usd(value: float) -> str:
    """Format USD value with commas."""
    return f"${value:,.0f}"


def process_price_change(data: dict) -> None:
    """
    Process a price_change event and alert on large trades.
    
    Per https://docs.polymarket.com/developers/CLOB/websocket/market-channel:
    price_changes contain: asset_id, price, size, side, best_bid, best_ask
    
    Note: Each trade creates paired entries (buy one side = sell the other).
    We only alert on BUY side to avoid duplicate notifications for the same wager.
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
        
        # Calculate approximate USD value
        # size is in shares, price is probability (0-1)
        # USD spent ≈ size * price for a BUY
        usd_value = size * price
        
        # Get outcome name
        outcome_name = TOKEN_NAMES.get(asset_id, "Unknown")
        
        # Log all trades for analysis
        log_entry = (
            f"{timestamp} | {outcome_name} | {side} | "
            f"size={size:.0f} | price={price:.2f} | "
            f"usd={usd_value:.2f} | bid={best_bid} ask={best_ask}"
        )
        log_event(log_entry)
        
        # Only alert on BUY side to avoid duplicate notifications
        # (each trade has a BUY and SELL entry for the paired outcomes)
        if side != "BUY":
            continue
        
        # Check threshold
        if usd_value >= USD_THRESHOLD:
            potential_profit = size * (1 - price)
            
            msg = (
                f"🏈 LARGE NFL WAGER\n\n"
                f"BET: {outcome_name} ML\n"
                f"{format_usd(usd_value)} @ {price:.0%}\n"
                f"Potential win: {format_usd(potential_profit)}\n"
                f"Market: Rams vs Panthers"
            )
            
            print(f"\n{'='*50}")
            print(f"[ALERT] {msg}")
            print(f"{'='*50}\n")
            
            market_url = "https://polymarket.com/event/nfl-la-car-2026-01-10"
            send_pushover(msg, market_url)


def run_monitor():
    """Main monitoring loop with reconnection logic."""
    print(f"[INFO] Starting NFL Large Wager Monitor")
    print(f"[INFO] Market: Rams vs Panthers Moneyline")
    print(f"[INFO] Threshold: {format_usd(USD_THRESHOLD)}")
    print(f"[INFO] WebSocket: {WS_URL}")
    print(f"[INFO] Subscribing to {len(ASSET_IDS)} tokens...")
    print()
    
    while True:
        try:
            ws = create_connection(WS_URL)
            print(f"[INFO] Connected to WebSocket")
            
            # Subscribe to market channel per docs
            # https://docs.polymarket.com/developers/CLOB/websocket/market-channel
            subscribe_msg = {
                "type": "market",
                "assets_ids": ASSET_IDS
            }
            ws.send(json.dumps(subscribe_msg))
            print(f"[INFO] Subscribed to market channel")
            
            while True:
                try:
                    message = ws.recv()
                    raw_data = json.loads(message)
                    
                    # Handle both list (initial book) and dict (price_change) responses
                    # Initial book response comes as a list per template.js behavior
                    if isinstance(raw_data, list):
                        for item in raw_data:
                            event_type = item.get("event_type")
                            if event_type == "book":
                                last_price = item.get("last_trade_price", "N/A")
                                print(f"[INFO] Received orderbook snapshot, last_trade_price={last_price}")
                        continue
                    
                    data = raw_data
                    event_type = data.get("event_type")
                    
                    if event_type == "book":
                        # Orderbook snapshot
                        last_price = data.get("last_trade_price", "N/A")
                        print(f"[INFO] Received orderbook snapshot, last_trade_price={last_price}")
                    
                    elif event_type == "price_change":
                        # Trade occurred - check for large wagers
                        process_price_change(data)
                    
                    else:
                        # Unknown event type, log it
                        print(f"[DEBUG] Unknown event: {event_type}")
                        
                except WebSocketConnectionClosedException:
                    print("[WARN] WebSocket connection closed, reconnecting...")
                    break
                    
        except Exception as e:
            print(f"[ERROR] WebSocket error: {e}")
            
        # Wait before reconnecting
        print("[INFO] Reconnecting in 5 seconds...")
        time.sleep(5)


if __name__ == "__main__":
    run_monitor()
