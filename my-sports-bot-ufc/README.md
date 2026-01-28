# UFC Whale Monitor Bot

Real-time monitoring of Polymarket UFC fight markets for whale activity using the Polymarket Data API.

## Workflow Overview

This bot uses the most efficient approach for whale detection:

1. **Market Discovery** (Gamma API) - Fetches all markets for a UFC event
2. **Trade Monitoring** (Data API) - Polls executed trades for the event markets
3. **Alert System** (Pushover) - Sends notifications when trades exceed USD threshold

### Why Data API over Holders Polling?

| Approach | Speed | Missed Trades | API Calls |
|----------|-------|---------------|-----------|
| Data API polling (this bot) | Near real-time (seconds) | Minimal | Moderate |
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
- **Trades (Data API)**: https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets

## How It Works

1. Fetches all markets for the specified UFC event from Gamma API
2. Extracts all `clobTokenIds` (one per outcome per market)
3. Polls the Data API `/trades` endpoint for executed trades in the event markets
4. Deduplicates trades based on transaction hash/timestamp
5. Calculates USD value (`size * price`) and alerts if above threshold

## Output

- Console logs all activity
- Saves all trades to `logs/ufc_<event_slug>.log`
- Sends Pushover notification for large wagers

## Notes

- Alerts include trade side (BUY/SELL)
- Supports both exact event slug and keyword search
- Polling interval is short to minimize delays
- The Data API `/trades` feed is used to avoid order-book `price_change` noise from placed/canceled orders
