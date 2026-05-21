# UFC Whale Monitor Bot

Real-time monitoring of Polymarket UFC fight markets for whale activity using the CLOB WebSocket API.

## Workflow Overview

This bot uses the most efficient approach for whale detection:

1. **Market Discovery** (Gamma API) - Fetches all markets for a UFC event
2. **Real-time Monitoring** (CLOB WebSocket) - Subscribes to `last_trade_price` events to detect executed trades
3. **Alert System** (Pushover + X) - Sends notifications and text-only X posts when trades exceed USD threshold

### Why WebSocket over Polling?

| Approach | Speed | Missed Trades | API Calls |
|----------|-------|---------------|-----------|
| WebSocket (this bot) | Real-time (~ms) | None | 1 connection |
| Polling `/holders` | Delayed (30s+) | Possible | Many per minute |

## Usage

```bash
# Monitor all active UFC fights (default)
./run_ufc_monitor.sh

# Explicit "all"
./run_ufc_monitor.sh all

# Monitor a single fight by event slug
./run_ufc_monitor.sh ufc-jus3-pad-2026-01-24

# Using keyword search (if slug unknown)
python3 monitor_ufc_large_wagers.py "gaethje pimblett"
```

## Threshold

Set the whale alert threshold in `my-sports-bot-ufc/.env`:

```bash
THRESHOLD=1000
```

## Setup

1. Copy `.env.example` to `.env`
2. Add your Pushover credentials and X OAuth 1.0a credentials
3. Run the bot

```bash
cp .env.example .env
# Edit .env with your Pushover and X credentials
./run_ufc_monitor.sh <event_slug>
```

Required X posting values:

```bash
X_API_KEY=...
X_API_SECRET=...
X_ACCESS_TOKEN=...
X_ACCESS_TOKEN_SECRET=...
```

## API References

- **Gamma API (markets)**: https://docs.polymarket.com/api-reference/core/get-market
- **WebSocket Overview**: https://docs.polymarket.com/developers/CLOB/websocket/wss-overview
- **Market Channel**: https://docs.polymarket.com/developers/CLOB/websocket/market-channel

## How It Works

1. Fetches all markets for the specified UFC event from Gamma API
2. Extracts all `clobTokenIds` (one per outcome per market)
3. Opens WebSocket connection to `wss://ws-subscriptions-clob.polymarket.com/ws/market`
4. Subscribes to the `market` channel with all token IDs
5. Listens for `last_trade_price` events containing:
   - `asset_id`: Token being traded
   - `size`: Number of shares traded
   - `price`: Trade price (0-1)
   - `side`: BUY or SELL
6. Calculates USD value (`size * price`) and alerts if above threshold

## Output

- Console logs all activity
- Saves all trades to `logs/ufc_<event_slug>.log`
- Sends Pushover notification for large wagers
- Posts a short text-only X alert through official OAuth 1.0a user context using `POST /2/tweets`
- Skips X posts when the bet price is already displayed as 100%, while still sending the Pushover alert

## Notes

- Alerts rely on `last_trade_price` (executed trades). `price_change` is emitted when orders are placed or canceled, so it can create false whale alerts if used for detection. See the Market Channel docs for details: https://docs.polymarket.com/developers/CLOB/websocket/market-channel.md
- Only BUY side triggers alerts (avoids duplicate notifications)
- X alert format mirrors the Pushover details with a flashier title line: `🐳  UFC Whale Alert 🐳`
- X posting failures are logged and do not stop Pushover alerts or the monitor loop
- Supports both exact event slug and keyword search
- Auto-reconnects on WebSocket disconnection
