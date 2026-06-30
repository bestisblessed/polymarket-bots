#!/usr/bin/env python3
"""
One-time execution script for whale monitoring with Pushover notifications.
Deduplicates using whale_alerts.jsonl instead of separate state file.
For new whales: adds historical trades to deduplication but doesn't send notifications.
"""

import json
import requests
import os
from datetime import datetime, timezone
from collections import defaultdict
import sys
import time

# Load environment variables from .env file (like @my-sports-bot)
def load_dotenv():
    """Load .env file if it exists."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        # Split on first =, strip whitespace from both sides
                        key, value = [part.strip() for part in line.split("=", 1)]
                        # Remove surrounding quotes from value
                        value = value.strip('"\'')
                        os.environ[key] = value
            # print(f"Loaded .env from {env_path}")
            return True
        except Exception as e:
            print(f"Error loading .env from {env_path}: {e}")
            return False
    else:
        print(f"No .env file found at {env_path}")
        return False

# Load .env first
load_dotenv_success = load_dotenv()

# Now load environment variables
PUSHOVER_API_TOKEN = os.getenv("PUSHOVER_API_TOKEN")
PUSHOVER_GROUP_KEY = os.getenv("PUSHOVER_GROUP_KEY")

if not PUSHOVER_API_TOKEN or not PUSHOVER_GROUP_KEY:
    if load_dotenv_success:
        print("WARNING: PUSHOVER_API_TOKEN or PUSHOVER_GROUP_KEY not found in .env after loading")
        print("Expected format in .env:")
        print('PUSHOVER_API_TOKEN="your_token_here"')
        print('PUSHOVER_GROUP_KEY="your_group_key_here"')
    else:
        print("WARNING: No .env file found and PUSHOVER_API_TOKEN/PUSHOVER_GROUP_KEY not set")
        print("Create .env file with:")
        print('PUSHOVER_API_TOKEN="your_token_here"')
        print('PUSHOVER_GROUP_KEY="your_group_key_here"')
    PUSHOVER_ENABLED = False
else:
    PUSHOVER_ENABLED = True
    # print(f"✓ Pushover enabled: Token={PUSHOVER_API_TOKEN[:8]}..., Group={PUSHOVER_GROUP_KEY[:8]}...")
    # print(f"  Full token preview: {PUSHOVER_API_TOKEN[:16]}... (loaded from .env)")

# Configuration - Wallet addresses for the whales
WHALES = {
    "0xLuck": "0xdba78eaec18da2455d4b78de38828c2d91f0ae61",
    #"Iam100x": "0x804600942f9044bf4f4ec7f1815b186184e60a1b",
    #"RootAccessed": "0x066d64fa7b2e352b9000a51c6b56f53128cce6e6",
    #"CoffeeOverCode": "0xf0badb774d036601892ac751d1a25d8492dfe4cb",
    "sakuralover": "0x169527179bbc4bd99288585fc39eb0e117bf2842",
    "aussietoken": "0x2589876f7934d8b9ed551e911e1b50dabbcc6868",
    "George.Smiley": "0x2110ba2a1e18840109482ff4ddc547baeff45850",
}
API_URL = "https://data-api.polymarket.com/activity"
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"
DATA_DIR = "data"
ALERTS_FILE = os.path.join(DATA_DIR, "whale_alerts.jsonl")
LIMIT = 100  # Events to fetch per whale

def send_pushover_notification(message, sound="pushover"):
    """Send notification to Pushover with default title."""
    if not PUSHOVER_ENABLED:
        print(f"[PUSHOVER SKIPPED] {message[:100]}...")
        return False

    try:
        payload = {
            "token": PUSHOVER_API_TOKEN,
            "user": PUSHOVER_GROUP_KEY,
            "message": message,
            "sound": sound,
            "timestamp": int(time.time()),
            "priority": 0  # Default priority
        }

        print(f"Sending Pushover: {message[:100]}... ({len(message)} chars, sound={sound})")
        resp = requests.post(PUSHOVER_URL, data=payload, timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            if result.get("status") == 1:
                print(f"✓ Pushover sent successfully: {len(message)} chars")
                return True
            else:
                print(f"✗ Pushover API error: {result}")
                return False
        else:
            print(f"✗ Pushover HTTP {resp.status_code}: {resp.text[:100]}")
            return False

    except Exception as e:
        print(f"✗ Pushover exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_processed_txs():
    """Get set of TX hashes already processed from whale_alerts.jsonl."""
    processed = set()
    whale_txs = defaultdict(set)  # Track TXs per whale for new whale detection

    if os.path.exists(ALERTS_FILE):
        try:
            with open(ALERTS_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        tx = event.get("tx")
                        username = event.get("username")
                        if tx and tx != "N/A":
                            processed.add(tx)
                            if username:
                                whale_txs[username].add(tx)
                    except json.JSONDecodeError:
                        print(f"  Warning: Skipping corrupted line in {ALERTS_FILE}")
                        continue
        except Exception as e:
            print(f"  Error reading {ALERTS_FILE}: {e}")

    print(f"  Loaded {len(processed)} already processed TXs from {ALERTS_FILE}")

    # Check which whales are new (no TXs in file yet)
    new_whales = []
    for username in WHALES:
        if username not in whale_txs:
            new_whales.append(username)
            print(f"  New whale detected: {username} (no previous TXs found)")

    return processed, new_whales

def fetch_activity(wallet, offset=0, limit=LIMIT):
    """Fetch recent activity for a wallet with detailed logging."""
    params = {"user": wallet, "limit": limit, "offset": offset}
    try:
        # print(f"    API call: {API_URL}?user={wallet[:10]}...&limit={limit}")
        resp = requests.get(API_URL, params=params, timeout=15)
        # print(f"    Response: {resp.status_code} ({len(resp.content)} bytes)")
        
        if resp.status_code == 200:
            try:
                data = resp.json()
                if isinstance(data, list):
                    print(f"    ✓ Success: {len(data)} events returned")
                    return data
                else:
                    print(f"    ✗ Unexpected response format: {type(data)}")
                    return []
            except json.JSONDecodeError as e:
                print(f"    ✗ JSON decode error: {e}")
                print(f"    Raw response preview: {str(resp.text)[:100]}")
                return []
        elif resp.status_code == 404:
            print(f"    ✗ Wallet not found or no activity (404)")
            return []
        elif resp.status_code == 429:
            print(f"    ✗ Rate limited (429) - waiting...")
            return []
        else:
            print(f"    ✗ API error {resp.status_code}: {resp.text[:100]}")
            return []
    except requests.exceptions.Timeout:
        print(f"    ✗ API timeout after 15s")
        return []
    except requests.exceptions.ConnectionError as e:
        print(f"    ✗ Connection error: {e}")
        return []
    except Exception as e:
        print(f"    ✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return []

def group_trades_by_cron_run(all_new_trades):
    """
    Group trades that occurred within the same cron run period.
    Groups by market title + side only (no time window - all new trades in run get grouped).
    """
    if not all_new_trades:
        return []

    # Group by market title + side
    market_groups = defaultdict(list)

    for trade in all_new_trades:
        title = trade.get("title", "Unknown Market")
        side = trade.get("side", "").lower()
        market_groups[(title, side)].append(trade)

    # Convert to list of groups
    grouped = [trades for (title, side), trades in market_groups.items() if len(trades) >= 1]

    print(f"    Grouped {len(all_new_trades)} trades into {len(grouped)} market groups")
    return grouped

def format_grouped_alert(group, username, wallet, is_new_whale=False):
    """Format alert for grouped trades, save to JSONL, and send Pushover notification."""
    # Group is always a list of 1+ trades for same market/side
    num_trades = len(group)
    first_trade = group[0]
    side = first_trade.get("side", "").upper()
    title = first_trade.get("title", "")
    outcome = first_trade.get("outcome", "Unknown")

    # Time range for this group
    first_ts_obj = datetime.fromtimestamp(group[0].get("timestamp", 0), timezone.utc)
    last_ts_obj = datetime.fromtimestamp(group[-1].get("timestamp", 0), timezone.utc)
    first_ts = first_ts_obj.strftime("%Y-%m-%d %H:%M:%S UTC")
    last_ts = last_ts_obj.strftime("%Y-%m-%d %H:%M:%S UTC")
    time_range = f"{first_ts} to {last_ts}" if num_trades > 1 else first_ts

    if num_trades == 1:
        trade = group[0]
        ts = first_ts
        size = trade.get("size", "0")
        price = trade.get("price", "0")
        usdc = trade.get("usdcSize", "0")
        tx = trade.get("transactionHash", "") if trade.get("transactionHash") else "N/A"

        # Title: Default (no custom title)
        pushover_title = None  # Will use default Pushover title

        # Message: New format - Whale ACTION shares MARKET with profile link (no TX line)
        shares_line = f"{size} shares @ {price} (${usdc})"

        profile_link = f"https://polymarket.com/@{username}"

        alert_message = f"{username} {side} {shares_line}\n{title}\nOutcome: {outcome}\n\n{profile_link}"

        alert = f"🚨 {username} {side} ORDER: {title} - {size} @ {price} (${usdc} USDC) -> {outcome} | Time: {ts}"

        # Save individual event
        alert_data = {
            "username": username,
            "wallet": wallet,
            "side": side,
            "title": title,
            "size": size,
            "price": price,
            "usdc": usdc,
            "outcome": outcome,
            "tx": trade.get("transactionHash"),
            "timestamp": ts,
            "full_event": trade,
            "grouped": False,
            "num_fills": 1,
            "run_time": datetime.now(timezone.utc).isoformat(),
            "pushover_message": alert_message,
            "pushover_sent": False,  # Will be updated after sending
            "new_whale_initialization": is_new_whale
        }

        # Send Pushover notification (only if not a new whale's historical data)
        pushover_success = False
        if not is_new_whale:
            pushover_success = send_pushover_notification(alert_message)
        else:
            print(f"    New whale {username}: Skipping notification for historical trade, adding to deduplication only")
        alert_data["pushover_sent"] = pushover_success

        try:
            with open(ALERTS_FILE, "a") as f:
                f.write(json.dumps(alert_data) + "\n")
        except Exception as e:
            print(f"    Error writing alert to {ALERTS_FILE}: {e}")

        return [alert]

    # Multiple trades - summarize
    # Calculate totals with error handling
    sizes = []
    usdcs = []
    for t in group:
        try:
            sizes.append(float(t.get("size", 0)))
            usdcs.append(float(t.get("usdcSize", 0)))
        except (ValueError, TypeError):
            continue

    total_size = sum(sizes)
    total_usdc = sum(usdcs)
    avg_price = total_usdc / total_size if total_size > 0 else 0
    num_fills = len(group)

    # Shares line for multiple fills
    shares_line = f"{total_size:.0f} shares @ avg {avg_price:.2f} (${total_usdc:.0f})"

    # Title: Default (no custom title)
    pushover_title = None  # Will use default Pushover title

    # Message: New format - Whale ACTION shares MARKET with profile link (no TX line)
    market_line = title

    profile_link = f"https://polymarket.com/@{username}"

    alert_message = f"{username} {side} {shares_line}\n{market_line}\nOutcome: {outcome}\n\n{profile_link}"

    alert = (f"🚨 {username} {side} ORDER ({num_fills} fills in this run): {title} - "
             f"{total_size:.0f} total shares @ avg {avg_price:.2f} "
             f"(${total_usdc:.0f} USDC) -> {outcome} | "
             f"Time: {time_range}")

    # Send Pushover for grouped alert (only if not a new whale's historical data)
    pushover_success = False
    if not is_new_whale:
        pushover_success = send_pushover_notification(alert_message, sound="long")
    else:
        print(f"    New whale {username}: Skipping notification for historical trades, adding to deduplication only")

    # Save individual events with group info
    for i, trade in enumerate(group):
        try:
            size = float(trade.get("size", 0))
            price = float(trade.get("price", 0))
            usdc = float(trade.get("usdcSize", 0))
        except (ValueError, TypeError):
            size = price = usdc = 0

        alert_data = {
            "username": username,
            "wallet": wallet,
            "side": side,
            "title": title,
            "size": trade.get("size", "0"),
            "price": trade.get("price", "0"),
            "usdc": trade.get("usdcSize", "0"),
            "outcome": outcome,
            "tx": trade.get("transactionHash"),
            "timestamp": datetime.fromtimestamp(trade.get("timestamp", 0), timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "full_event": trade,
            "grouped": True,
            "group_size": num_fills,
            "total_size": total_size,
            "total_usdc": total_usdc,
            "avg_price": avg_price,
            "is_first_in_group": i == 0,
            "is_last_in_group": i == num_fills - 1,
            "run_time": datetime.now(timezone.utc).isoformat(),
            "group_duration_min": round((last_ts_obj - first_ts_obj).total_seconds() / 60, 1),
            "pushover_message": alert_message,
            "pushover_sent": pushover_success,
            "new_whale_initialization": is_new_whale
        }

        try:
            with open(ALERTS_FILE, "a") as f:
                f.write(json.dumps(alert_data) + "\n")
        except Exception as e:
            print(f"    Error writing grouped alert {i+1}/{num_fills} to {ALERTS_FILE}: {e}")

    return [alert]

def main():
    """Main execution - run once, check all whales."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f"=== Whale Check Started: {now} ===")
    # print(f"Working directory: {os.getcwd()}")
    # print(f"Python: {sys.executable}")
    # print(f"Pushover: {'Enabled' if PUSHOVER_ENABLED else 'Disabled (missing .env)'}")

    # Load processed TXs and detect new whales
    processed_txs, new_whales = get_processed_txs()

    # Ensure data directory and alerts file exist
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(ALERTS_FILE):
        with open(ALERTS_FILE, "w") as f:
            pass  # Create empty file
        print(f"Created new alerts file: {ALERTS_FILE}")
    
    # print(f"Loaded state from {ALERTS_FILE} (deduplication by TX hash)")
    
    # Record start time for run duration calculation
    run_start_time = time.time()

    total_alerts = 0
    total_new_events = 0
    all_whale_trades = []  # Collect all new trades for run-wide analysis

    for username, wallet in WHALES.items():
        try:
            is_new_whale = username in new_whales
            status_msg = "NEW WHALE - Initializing" if is_new_whale else "Monitoring"
            print(f"\n--- Checking {username} ({wallet[:10]}...) - {status_msg} ---")

            activity = fetch_activity(wallet)
            if not activity:
                print(f"  No activity data returned for {username}")
                continue
            
            # print(f"  Raw API returned {len(activity)} total events")
            
            # Filter to BUY/SELL only and check for duplicates
            buy_sell_recent = []
            skipped_duplicates = 0

            for event in activity:
                side = event.get("side", "").lower()
                if side in ["buy", "sell"]:
                    tx = event.get("transactionHash", "")
                    if tx and tx in processed_txs:
                        skipped_duplicates += 1
                        continue
                    buy_sell_recent.append(event)
                    all_whale_trades.append({**event, "username": username, "wallet": wallet})

            if skipped_duplicates > 0:
                print(f"  Skipped {skipped_duplicates} already processed trades")

            total_new_events += len(buy_sell_recent)

            if buy_sell_recent:
                print(f"  Processing {len(buy_sell_recent)} new BUY/SELL events:")

                # Group by market within this whale's new events
                grouped_trades = group_trades_by_cron_run(buy_sell_recent)
                for i, group in enumerate(grouped_trades, 1):
                    alerts = format_grouped_alert(group, username, wallet, is_new_whale)
                    for alert in alerts:
                        print(f"    {i}. {alert}")
                    # Only count as alerts if notifications were actually sent
                    if not is_new_whale:
                        total_alerts += 1
            else:
                print(f"  No new BUY/SELL trades for {username}")

        except KeyboardInterrupt:
            print(f"\nInterrupted during {username}")
            break
        except Exception as e:
            print(f"  Unexpected error checking {username}: {e}")
            import traceback
            traceback.print_exc()
            continue

    run_end_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    run_duration = time.time() - run_start_time
    print(f"\n=== Check Complete: {total_alerts} alerts from {total_new_events} events | {run_end_time} ===")
    print(f"Run duration: {run_duration:.1f}s | Deduplication: {len(processed_txs)} TXs loaded")
    # print(f"Alerts: {ALERTS_FILE} (appended {total_new_events} new events)")
    if PUSHOVER_ENABLED:
        print(f"Pushover: {total_alerts} notifications sent this run")
    else:
        print("Pushover: Disabled - create .env file to enable notifications")

if __name__ == "__main__":
    main()
