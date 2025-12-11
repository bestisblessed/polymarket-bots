#!/usr/bin/env python3
# Minimal AltCreamster wallet watcher using Polymarket Data API activity endpoint.
# Docs: https://docs.polymarket.com/data/activity

import json
import os
from pathlib import Path
import requests
from datetime import datetime, timezone

env_path = Path(__file__).with_name('.env')
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if '=' in line and not line.strip().startswith('#'):
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip().strip('"\'')

# Configuration
ALERTS_FILE = 'creamster_alerts.jsonl'
WALLET_ADDRESS = '0x899c7076e1e81f2d6bf5c78c140a943752fded9a'
USERNAME = 'AltCreamster'

def get_processed_txs():
    """Get set of TX hashes already processed from creamster_alerts.jsonl."""
    processed = set()

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
                        if tx and tx != "N/A":
                            processed.add(tx)
                    except json.JSONDecodeError:
                        print(f"Warning: Skipping corrupted line in {ALERTS_FILE}")
                        continue
        except Exception as e:
            print(f"Error reading {ALERTS_FILE}: {e}")

    print(f"Loaded {len(processed)} already processed TXs from {ALERTS_FILE}")
    return processed

def send_pushover_notification(message):
    """Send notification to Pushover."""
    try:
        response = requests.post(
            'https://api.pushover.net/1/messages.json',
            data={
                'token': os.environ['PUSHOVER_API_TOKEN'],
                'user': os.environ['PUSHOVER_GROUP_KEY'],
                'message': message,
            },
            timeout=10,
        )
        if response.status_code == 200:
            print("✓ Pushover notification sent successfully")
            return True
        else:
            print(f"✗ Pushover failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"✗ Pushover exception: {e}")
        return False

def main():
    """Main execution - check AltCreamster wallet for new trades."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f"=== AltCreamster Check Started: {now} ===")

    # Load processed TXs for deduplication
    processed_txs = get_processed_txs()
    is_initialization = len(processed_txs) == 0

    # Ensure alerts file exists
    if not os.path.exists(ALERTS_FILE):
        with open(ALERTS_FILE, "w") as f:
            pass  # Create empty file
        print(f"Created new alerts file: {ALERTS_FILE}")

    if is_initialization:
        print(f"  First run detected - initializing deduplication, notifications will be skipped")

    # Fetch recent activity
    print(f"Fetching activity for {USERNAME} ({WALLET_ADDRESS[:10]}...)")
    try:
        response = requests.get(
            'https://data-api.polymarket.com/activity',
            params={'user': WALLET_ADDRESS, 'limit': 50, 'offset': 0},
            timeout=15,
        )
        if response.status_code != 200:
            print(f"✗ API error {response.status_code}: {response.text[:100]}")
            return

        activity = response.json()
        print(f"✓ Fetched {len(activity)} events")
    except Exception as e:
        print(f"✗ Failed to fetch activity: {e}")
        return

    # Filter to BUY/SELL trades and check for duplicates
    new_trades = []
    skipped_duplicates = 0

    for trade in activity:
        side = trade.get('side', '').lower()
        if side in ['buy', 'sell']:
            tx_hash = trade.get('transactionHash')
            if tx_hash and tx_hash in processed_txs:
                skipped_duplicates += 1
                continue
            new_trades.append(trade)

    if skipped_duplicates > 0:
        print(f"Skipped {skipped_duplicates} already processed trades")

    if not new_trades:
        print("No new trades found")
        return

    print(f"Processing {len(new_trades)} new trades")

    # Process new trades (in chronological order - oldest first)
    for trade in new_trades:
        # Create notification message
        profile_link = f"https://polymarket.com/@{USERNAME}"
        message = (
            f"{USERNAME} {trade.get('side', '').upper()} {trade.get('size') or trade.get('amount')} @ {trade.get('price')}"
            f" (${trade.get('usdcSize')})\n"
            f"Outcome: {trade.get('outcome', '')}\n"
            f"Market: {trade.get('title', '')}\n"
            f"Tx: {trade.get('transactionHash', '')}\n\n"
            f"{profile_link}"
        )

        # Send notification (skip during initialization)
        pushover_success = False
        if not is_initialization:
            pushover_success = send_pushover_notification(message)
        else:
            print(f"    Initialization: Skipping notification for historical trade, adding to deduplication only")

        # Save to JSONL file
        alert_data = {
            "username": USERNAME,
            "wallet": WALLET_ADDRESS,
            "side": trade.get('side', '').upper(),
            "title": trade.get('title', ''),
            "size": trade.get('size', '0'),
            "price": trade.get('price', '0'),
            "usdc": trade.get('usdcSize', '0'),
            "outcome": trade.get('outcome', ''),
            "tx": trade.get('transactionHash', ''),
            "timestamp": datetime.fromtimestamp(trade.get('timestamp', 0), timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "full_event": trade,
            "run_time": datetime.now(timezone.utc).isoformat(),
            "pushover_message": message,
            "pushover_sent": pushover_success
        }

        try:
            with open(ALERTS_FILE, "a") as f:
                f.write(json.dumps(alert_data) + "\n")
        except Exception as e:
            print(f"Error writing alert to {ALERTS_FILE}: {e}")

    if is_initialization:
        print(f"✓ Initialized with {len(new_trades)} historical trades (notifications skipped)")
    else:
        print(f"✓ Processed {len(new_trades)} new trades")

if __name__ == "__main__":
    main()
