# UFC Whale Monitor Bot

Real-time monitoring of Polymarket UFC fight markets for whale activity using the CLOB WebSocket API.

## Workflow Overview

This bot uses the most efficient approach for whale detection:

1. **Market Discovery** (Gamma API) - Fetches all markets for a UFC event
2. **Real-time Monitoring** (CLOB WebSocket) - Subscribes to `price_change` events for instant trade detection
3. **Alert System** (Pushover) - Sends notifications when trades exceed USD threshold

For open order monitoring (pending orders before fills), use the separate open-order script described below.

### Why WebSocket over Polling?

| Approach | Speed | Missed Trades | API Calls |
|----------|-------|---------------|-----------|
| WebSocket (this bot) | Real-time (~ms) | None | 1 connection |
| Polling `/holders` | Delayed (30s+) | Possible | Many per minute |

## Usage

```bash
# Basic usage with event slug
./run_ufc_monitor.sh ufc-jus3-pad-2026-01-24

# With custom threshold
./run_ufc_monitor.sh ufc-jus3-pad-2026-01-24 10000

# Using keyword search (if slug unknown)
python3 monitor_ufc_large_wagers.py "gaethje pimblett" --threshold 5000
```

### Open Order Monitoring (Pending Orders)

```bash
# Basic usage with event slug
./run_ufc_open_orders.sh ufc-jus3-pad-2026-01-24

# With custom threshold
./run_ufc_open_orders.sh ufc-jus3-pad-2026-01-24 10000

# Using keyword search (if slug unknown)
python3 monitor_ufc_open_orders.py "gaethje pimblett" --threshold 5000
```

## Setup

1. Copy `.env.example` to `.env`
2. Add your Pushover credentials
3. Run the bot

```bash
cp .env.example .env
# Edit .env with your Pushover credentials
./run_ufc_monitor.sh <event_slug>
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
5. Listens for `price_change` events containing:
   - `asset_id`: Token being traded
   - `size`: Number of shares
   - `price`: Trade price (0-1)
   - `side`: BUY or SELL
6. Calculates USD value (`size * price`) and alerts if above threshold

## Output

- Console logs all activity
- Saves all trades to `logs/ufc_<event_slug>.log`
- Sends Pushover notification for large wagers

## Open Orders vs Fills

- **Large wager monitor (`monitor_ufc_large_wagers.py`)**: alerts on `price_change` trade events (fills only).
- **Open order monitor (`monitor_ufc_open_orders.py`)**: alerts on `book` updates (pending orders in the order book).

## Notes

- Only BUY side triggers alerts (avoids duplicate notifications)
- Supports both exact event slug and keyword search
- Auto-reconnects on WebSocket disconnection
