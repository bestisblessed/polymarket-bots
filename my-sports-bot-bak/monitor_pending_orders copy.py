"""
Monitor pending orders (order book) for NFL game markets using WebSocket for real-time detection.

This script uses Polymarket's WebSocket API to monitor the CLOB (Central Limit Order Book) in real-time,
providing instant detection of large pending orders as soon as they're placed. This is much more
proactive than polling, as it catches orders immediately and never misses fast-filling orders.

- Real-time mode: `python monitor_pending_orders.py` monitors all active NFL game markets via WebSocket
- Single-game mode: `python monitor_pending_orders.py --game-id <market_id>`

When run, the script sends Pushover alerts when it detects pending orders larger than USD $10,000.

WebSocket API: wss://ws-subscriptions-clob.polymarket.com/ws/market
Documentation: https://github.com/huakunshen/polymarket-kit
"""
import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Set

import requests
import websocket
from dotenv import load_dotenv

load_dotenv()

WS_ENDPOINT = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
MARKET_ENDPOINT = "https://gamma-api.polymarket.com/markets"
PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json"
GAMES_FILE = "data/nfl_games.json"
STATE_PATH = os.path.join("data", "pending_orders_state.json")
# ORDER_THRESHOLD_USD = 1  # Lowered for testing (normally 10_000)
ORDER_THRESHOLD_USD = 100_000  # Lowered for testing (normally 10_000)
SUPPORTED_TYPES = {"spreads", "totals", "moneyline"}

# Global state
ws_client = None
markets_by_token: Dict[str, Dict] = {}  # token_id -> market info
outcomes_by_token: Dict[str, str] = {}  # token_id -> outcome name
seen_orders: Set[str] = set()  # Track seen order IDs to avoid duplicates
state_lock = threading.Lock()


def ensure_data_dir() -> None:
    os.makedirs("data", exist_ok=True)


def send_pushover(message: str, url: str = None) -> None:
    token = os.environ.get("PUSHOVER_API_TOKEN")
    user = os.environ.get("PUSHOVER_GROUP_KEY")
    if not token or not user:
        print("Pushover credentials not found in .env, skipping notification")
        return
    data = {"token": token, "user": user, "message": message, "html": 1}
    if url:
        data["url"] = url
        data["url_title"] = "View Profile"
    resp = requests.post(PUSHOVER_ENDPOINT, data=data, timeout=10)
    if resp.ok:
        print("Pushover notification sent")
    else:
        print(f"Pushover failed: {resp.status_code}")


def fetch_market_details(market_id: str) -> Optional[Dict]:
    """Fetch market details to get conditionId and other metadata."""
    try:
        resp = requests.get(f"{MARKET_ENDPOINT}/{market_id}", timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"Error fetching market {market_id}: {e}")
    return None


def load_nfl_games() -> List[Dict]:
    """Load NFL game markets from saved file."""
    if not os.path.exists(GAMES_FILE):
        print(f"Error: {GAMES_FILE} not found. Run get_nfl_games.py first.")
        sys.exit(1)
    
    with open(GAMES_FILE, "r", encoding="utf-8") as f:
        games = json.load(f)
    
    # Filter to supported types
    return [g for g in games if g.get("sportsMarketType") in SUPPORTED_TYPES]


def get_all_token_ids(games: List[Dict]) -> List[str]:
    """
    Extract all token IDs from NFL game markets.
    
    Markets have clobTokenIds field directly from Gamma API.
    Note: clobTokenIds may be a JSON string that needs parsing.
    """
    token_ids = []
    for game in games:
        clob_token_ids_raw = game.get("clobTokenIds", [])
        outcomes = game.get("outcomes", [])
        
        if not clob_token_ids_raw:
            continue
        
        # Parse clobTokenIds if it's a JSON string
        if isinstance(clob_token_ids_raw, str):
            try:
                clob_token_ids = json.loads(clob_token_ids_raw)
            except (json.JSONDecodeError, TypeError):
                # If parsing fails, skip this market
                continue
        else:
            clob_token_ids = clob_token_ids_raw
        
        if not isinstance(clob_token_ids, list):
            continue
        
        # Map token IDs to market and outcome info
        for idx, token_id in enumerate(clob_token_ids):
            if not token_id:
                continue
            token_ids.append(str(token_id))
            markets_by_token[str(token_id)] = game
            outcome_name = outcomes[idx] if idx < len(outcomes) else f"Outcome {idx}"
            outcomes_by_token[str(token_id)] = outcome_name
    
    return token_ids


def calculate_order_value(price: float, size: float) -> float:
    """Calculate USD value of an order."""
    return price * size


def format_order_info(price: float, size: float, market: Dict, outcome: str, side: str) -> str:
    """Format order information for display."""
    value_usd = price * size
    market_name = market.get("question", market.get("slug", "NFL market"))
    
    return (
        f"{market_name}\n"
        f"Side: {side}\n"
        f"Outcome: {outcome}\n"
        f"Price: ${price:.4f}\n"
        f"Size: {size:.2f} shares\n"
        f"Value: ${value_usd:,.2f}"
    )


def generate_order_id(price: str, size: str, side: str, asset_id: str) -> str:
    """Generate a unique order ID from order book data."""
    # Since WebSocket book events don't include order IDs, we create one from the data
    return f"{asset_id}:{side}:{price}:{size}"


def check_order_for_alert(price: float, size: float, asset_id: str, side: str) -> None:
    """Check if an order exceeds threshold and alert if new."""
    value_usd = calculate_order_value(price, size)
    
    if value_usd < ORDER_THRESHOLD_USD:
        return
    
    # Generate order ID
    order_id = generate_order_id(str(price), str(size), side, asset_id)
    
    # Check if we've seen this order before
    with state_lock:
        if order_id in seen_orders:
            print(f"   ⏭️  Order already seen, skipping alert")
            return
        seen_orders.add(order_id)
    
    # Get market and outcome info
    market = markets_by_token.get(asset_id, {})
    outcome = outcomes_by_token.get(asset_id, "Unknown")
    
    # Format and send alert
    order_info = format_order_info(price, size, market, outcome, side)
    message = f"LARGE PENDING {side} ORDER DETECTED:\n\n{order_info}"
    print(f"\n🚨🚨🚨 ALERT: {message}\n")
    send_pushover(message)


def on_message(ws, message: str) -> None:
    """Handle incoming WebSocket messages."""
    # #region agent log
    try:
        with open('/Users/td/Code/polymarket-bots/my-sports-bot/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"monitor_pending_orders.py:on_message","message":"Raw WebSocket message received","data":{"messageLength":len(message),"messagePreview":message[:200]},"timestamp":int(time.time()*1000)})+"\n")
    except: pass
    # #endregion
    try:
        data = json.loads(message)
        # #region agent log
        try:
            with open('/Users/td/Code/polymarket-bots/my-sports-bot/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"monitor_pending_orders.py:on_message","message":"JSON parsed successfully","data":{"dataType":type(data).__name__,"isList":isinstance(data,list),"isDict":isinstance(data,dict)},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        # Handle both list and dict responses
        if isinstance(data, list):
            # #region agent log
            try:
                with open('/Users/td/Code/polymarket-bots/my-sports-bot/.cursor/debug.log', 'a') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"monitor_pending_orders.py:on_message","message":"Processing list of messages","data":{"listLength":len(data)},"timestamp":int(time.time()*1000)})+"\n")
            except: pass
            # #endregion
            # Multiple messages in one payload
            for msg in data:
                process_single_message(msg)
        elif isinstance(data, dict):
            # #region agent log
            try:
                with open('/Users/td/Code/polymarket-bots/my-sports-bot/.cursor/debug.log', 'a') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"monitor_pending_orders.py:on_message","message":"Processing single dict message","data":{"eventType":data.get("event_type","missing"),"keys":list(data.keys())[:10]},"timestamp":int(time.time()*1000)})+"\n")
            except: pass
            # #endregion
            # Single message
            process_single_message(data)
        else:
            # #region agent log
            try:
                with open('/Users/td/Code/polymarket-bots/my-sports-bot/.cursor/debug.log', 'a') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"monitor_pending_orders.py:on_message","message":"Unexpected data type","data":{"dataType":type(data).__name__},"timestamp":int(time.time()*1000)})+"\n")
            except: pass
            # #endregion
            
    except json.JSONDecodeError as e:
        # #region agent log
        try:
            with open('/Users/td/Code/polymarket-bots/my-sports-bot/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"monitor_pending_orders.py:on_message","message":"JSON decode error","data":{"error":str(e),"messagePreview":message[:200]},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        print(f"Error parsing WebSocket message: {e}")
    except Exception as e:
        # #region agent log
        try:
            with open('/Users/td/Code/polymarket-bots/my-sports-bot/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"monitor_pending_orders.py:on_message","message":"Exception in on_message","data":{"error":str(e),"errorType":type(e).__name__},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        print(f"Error handling WebSocket message: {e}")


def process_single_message(data: Dict) -> None:
    """Process a single WebSocket message."""
    event_type = data.get("event_type")
    # #region agent log
    try:
        with open('/Users/td/Code/polymarket-bots/my-sports-bot/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"monitor_pending_orders.py:process_single_message","message":"Processing message","data":{"eventType":event_type,"allKeys":list(data.keys())},"timestamp":int(time.time()*1000)})+"\n")
    except: pass
    # #endregion
    
    if event_type == "book":
        print(f"📚 Order book update received for asset {data.get('asset_id', 'unknown')[:20]}...")
        handle_book_update(data)
    elif event_type == "price_change":
        print(f"💹 Price change event received")
        # Price changes might indicate new orders, but we focus on book updates
        pass
    elif event_type == "last_trade_price":
        print(f"💰 Trade execution event received")
        # Trade execution - not what we're monitoring
        pass
    else:
        # Unknown event type - might be subscription confirmation
        print(f"📨 Unknown event type: {event_type}")
        # #region agent log
        try:
            with open('/Users/td/Code/polymarket-bots/my-sports-bot/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"monitor_pending_orders.py:process_single_message","message":"Unknown event type - full data","data":{"eventType":event_type,"fullData":str(data)[:500]},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion


def handle_book_update(data: Dict) -> None:
    """Handle order book update events."""
    asset_id = data.get("asset_id")
    if not asset_id:
        return
    
    bids = data.get("bids", [])
    asks = data.get("asks", [])
    
    market = markets_by_token.get(asset_id, {})
    outcome = outcomes_by_token.get(asset_id, "Unknown")
    market_name = market.get("question", market.get("slug", "Unknown"))[:40]
    
    print(f"   Market: {market_name} | Outcome: {outcome}")
    print(f"   Bids: {len(bids)}, Asks: {len(asks)}")
    
    if bids:
        best_bid = bids[-1] if isinstance(bids, list) else bids
        bid_price = float(best_bid.get("price", 0))
        bid_size = float(best_bid.get("size", 0))
        bid_value = bid_price * bid_size
        print(f"   Best Bid: ${bid_price:.4f} x {bid_size:.2f} = ${bid_value:.2f}")
    
    if asks:
        best_ask = asks[0] if isinstance(asks, list) else asks
        ask_price = float(best_ask.get("price", 0))
        ask_size = float(best_ask.get("size", 0))
        ask_value = ask_price * ask_size
        print(f"   Best Ask: ${ask_price:.4f} x {ask_size:.2f} = ${ask_value:.2f}")
    
    # Check bids (buy orders)
    large_bids = 0
    for bid in bids:
        try:
            price = float(bid.get("price", 0))
            size = float(bid.get("size", 0))
            if price > 0 and size > 0:
                value = price * size
                if value >= ORDER_THRESHOLD_USD:
                    large_bids += 1
                check_order_for_alert(price, size, asset_id, "BUY")
        except (ValueError, TypeError):
            continue
    
    # Check asks (sell orders)
    large_asks = 0
    for ask in asks:
        try:
            price = float(ask.get("price", 0))
            size = float(ask.get("size", 0))
            if price > 0 and size > 0:
                value = price * size
                if value >= ORDER_THRESHOLD_USD:
                    large_asks += 1
                check_order_for_alert(price, size, asset_id, "SELL")
        except (ValueError, TypeError):
            continue
    
    if large_bids > 0 or large_asks > 0:
        print(f"   ⚠️  Found {large_bids} large bids and {large_asks} large asks (>= ${ORDER_THRESHOLD_USD})")
    print()  # Blank line for readability


def on_error(ws, error) -> None:
    """Handle WebSocket errors."""
    # #region agent log
    try:
        with open('/Users/td/Code/polymarket-bots/my-sports-bot/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"monitor_pending_orders.py:on_error","message":"WebSocket error occurred","data":{"error":str(error),"errorType":type(error).__name__},"timestamp":int(time.time()*1000)})+"\n")
    except: pass
    # #endregion
    print(f"WebSocket error: {error}")


def on_close(ws, close_status_code, close_msg) -> None:
    """Handle WebSocket close."""
    print(f"WebSocket connection closed: {close_status_code} - {close_msg}")
    print("Attempting to reconnect in 5 seconds...")
    time.sleep(5)
    connect_websocket()


def on_open(ws) -> None:
    """Handle WebSocket open - subscribe to all token IDs."""
    # #region agent log
    try:
        with open('/Users/td/Code/polymarket-bots/my-sports-bot/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"monitor_pending_orders.py:on_open","message":"WebSocket connection opened","data":{"endpoint":WS_ENDPOINT},"timestamp":int(time.time()*1000)})+"\n")
    except: pass
    # #endregion
    print("✅ WebSocket connection established")
    
    # Get all token IDs from NFL games
    games = load_nfl_games()
    token_ids = get_all_token_ids(games)
    
    if not token_ids:
        print("No token IDs found. Make sure get_nfl_games.py has been run.")
        ws.close()
        return
    
    print(f"Subscribing to {len(token_ids)} token IDs from {len(games)} markets...")
    
    # Subscribe to market channel
    subscribe_msg = {
        "type": "market",
        "assets_ids": token_ids
    }
    subscribe_json = json.dumps(subscribe_msg)
    # #region agent log
    try:
        with open('/Users/td/Code/polymarket-bots/my-sports-bot/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"post-fix","hypothesisId":"B","location":"monitor_pending_orders.py:on_open","message":"Sending subscription message","data":{"tokenCount":len(token_ids),"messageLength":len(subscribe_json),"firstTokenId":token_ids[0] if token_ids else None,"tokenIdsType":type(token_ids).__name__,"firstTokenType":type(token_ids[0]).__name__ if token_ids else None},"timestamp":int(time.time()*1000)})+"\n")
    except: pass
    # #endregion
    
    ws.send(subscribe_json)
    print(f"✅ Subscribed to {len(token_ids)} assets")
    print(f"Monitoring for orders > ${ORDER_THRESHOLD_USD:,.0f}...")
    print("Waiting for order book updates...\n")


def load_state() -> Set[str]:
    """Load state of seen orders."""
    if not os.path.exists(STATE_PATH):
        return set()
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
            # Flatten all seen order IDs from all markets
            all_ids = set()
            for market_state in state.values():
                all_ids.update(market_state.get("seen_order_ids", []))
            return all_ids
    except Exception:
        return set()


def save_state() -> None:
    """Save state of seen orders periodically."""
    ensure_data_dir()
    # Save in a format compatible with the old polling script
    state = {}
    with state_lock:
        # Group by market (we'll need to track this differently)
        # For now, just save all seen orders
        state["_all_seen_orders"] = list(seen_orders)
        state["_last_save"] = datetime.now().isoformat()
    
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def connect_websocket() -> None:
    """Connect to Polymarket WebSocket and start monitoring."""
    global ws_client
    
    # Load previously seen orders
    global seen_orders
    seen_orders = load_state()
    print(f"Loaded {len(seen_orders)} previously seen orders from state")
    
    # Create WebSocket connection
    ws = websocket.WebSocketApp(
        WS_ENDPOINT,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    
    ws_client = ws
    
    # Run forever with auto-reconnect
    ws.run_forever()


def monitor_single_market_websocket(market_id: str) -> None:
    """Monitor a single market via WebSocket."""
    print(f"Fetching market details for {market_id}...")
    market = fetch_market_details(market_id)
    if not market:
        print(f"Error: Could not fetch market {market_id}")
        sys.exit(1)
    
    print(f"Market found: {market.get('question', market.get('slug', 'Unknown'))}")
    
    # Get token IDs from this market
    clob_token_ids_raw = market.get("clobTokenIds", [])
    outcomes = market.get("outcomes", [])
    
    if not clob_token_ids_raw:
        print("Error: Market has no clobTokenIds")
        sys.exit(1)
    
    # Parse clobTokenIds if it's a JSON string
    if isinstance(clob_token_ids_raw, str):
        try:
            clob_token_ids = json.loads(clob_token_ids_raw)
        except (json.JSONDecodeError, TypeError):
            print("Error: Could not parse clobTokenIds as JSON")
            sys.exit(1)
    else:
        clob_token_ids = clob_token_ids_raw
    
    if not isinstance(clob_token_ids, list):
        print("Error: clobTokenIds is not a list")
        sys.exit(1)
    
    # Map token IDs
    for idx, token_id in enumerate(clob_token_ids):
        if not token_id:
            continue
        token_id_str = str(token_id)
        markets_by_token[token_id_str] = market
        outcome_name = outcomes[idx] if idx < len(outcomes) else f"Outcome {idx}"
        outcomes_by_token[token_id_str] = outcome_name
    
    print(f"Subscribing to {len(clob_token_ids)} token IDs...")
    
    # Load state
    global seen_orders
    seen_orders = load_state()
    
    # Create WebSocket connection
    def on_open_single(ws):
        # Ensure clob_token_ids is a list of strings
        token_ids_list = [str(tid) for tid in clob_token_ids if tid]
        subscribe_msg = {
            "type": "market",
            "assets_ids": token_ids_list
        }
        ws.send(json.dumps(subscribe_msg))
        print(f"✅ Subscribed to {len(token_ids_list)} assets")
        print(f"Monitoring for orders > ${ORDER_THRESHOLD_USD:,.0f}...\n")
    
    ws = websocket.WebSocketApp(
        WS_ENDPOINT,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open_single
    )
    
    global ws_client
    ws_client = ws
    
    # Run forever
    ws.run_forever()


def save_state_periodically() -> None:
    """Save state every 60 seconds."""
    while True:
        time.sleep(60)
        save_state()
        print(f"💾 State saved ({len(seen_orders)} seen orders)")


def parse_args(args: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor pending orders (order book) for NFL game markets via WebSocket"
    )
    parser.add_argument(
        "--game-id",
        help="Monitor a single market ID (default: monitor all markets)",
        default=None,
    )
    return parser.parse_args(args)


def main() -> None:
    ensure_data_dir()
    args = parse_args(sys.argv[1:])
    
    print("=" * 60)
    print("Polymarket Real-Time Order Book Monitor (WebSocket)")
    print("=" * 60)
    print(f"Alerts when a pending order exceeds ${ORDER_THRESHOLD_USD:,.2f}")
    print("Real-time detection - no polling delay!")
    print("=" * 60)
    print()
    
    # Start state saving thread
    state_thread = threading.Thread(target=save_state_periodically, daemon=True)
    state_thread.start()
    
    try:
        if args.game_id:
            monitor_single_market_websocket(args.game_id)
        else:
            connect_websocket()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        if ws_client:
            ws_client.close()
        save_state()
        print("State saved. Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
