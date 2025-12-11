#!/usr/bin/env python3
# Minimal AltCreamster wallet watcher using Polymarket Data API activity endpoint.
# Docs: https://docs.polymarket.com/data/activity

import os
from pathlib import Path
import requests

env_path = Path(__file__).with_name('.env')
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if '=' in line and not line.strip().startswith('#'):
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip().strip('"\'')

state_path = Path(__file__).with_name('last_seen_tx.txt')
last_seen = state_path.read_text().strip() if state_path.exists() else None

activity = requests.get(
    'https://data-api.polymarket.com/activity',
    params={'user': '0x899c7076e1e81f2d6bf5c78c140a943752fded9a', 'limit': 50, 'offset': 0},
    timeout=15,
).json()

new_trades = []
for trade in activity:
    tx_hash = trade.get('transactionHash')
    if not tx_hash:
        continue
    if tx_hash == last_seen:
        break
    if trade.get('side'):
        new_trades.append(trade)

if new_trades:
    state_path.write_text(new_trades[0].get('transactionHash', ''))
    for trade in reversed(new_trades):
        message = (
            f"AltCreamster {trade.get('side', '').upper()} {trade.get('size') or trade.get('amount')} @ {trade.get('price')}"
            f" (${trade.get('usdcSize')})\n"
            f"Outcome: {trade.get('outcome', '')}\n"
            f"Market: {trade.get('title', '')}\n"
            f"Tx: {trade.get('transactionHash', '')}"
        )
        requests.post(
            'https://api.pushover.net/1/messages.json',
            data={
                'token': os.environ['PUSHOVER_API_TOKEN'],
                'user': os.environ['PUSHOVER_GROUP_KEY'],
                'message': message,
            },
            timeout=10,
        )
