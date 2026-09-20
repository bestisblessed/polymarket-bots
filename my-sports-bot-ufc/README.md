# UFC Whale Monitor Bot

Real-time monitoring of Polymarket UFC fight markets for whale activity using the CLOB WebSocket API.

## Workflow Overview

This bot uses the most efficient approach for whale detection:

1. **Market Discovery** (Gamma API) - Fetches all markets for a UFC event
2. **Real-time Monitoring** (CLOB WebSocket) - Subscribes to `last_trade_price` events to detect executed trades
3. **UFC Card Art** (UFC.com) - Matches each fight date to the official upcoming event page and caches its desktop hero image
4. **Alert System** (Pushover + X) - Sends linked Pushover notifications and URL-free X posts with the matching card image

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

Daemon commands:

```bash
./run_ufc_monitor_daemon.sh start all
./run_ufc_monitor_daemon.sh restart all
./run_ufc_monitor_daemon.sh status
./run_ufc_monitor_daemon.sh logs
./run_ufc_monitor_daemon.sh stop
```

`start` waits 30 seconds by default for network readiness. `restart` waits 10 seconds by default.

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

The bot uses X's official `POST /2/media/upload` endpoint, then attaches the
returned media ID through `POST /2/tweets`. It uploads a card image once and
reuses that media ID until shortly before X's reported expiration time.

## API References

- **Gamma API (markets)**: https://docs.polymarket.com/api-reference/core/get-market
- **WebSocket Overview**: https://docs.polymarket.com/developers/CLOB/websocket/wss-overview
- **Market Channel**: https://docs.polymarket.com/developers/CLOB/websocket/market-channel
- **X media upload**: https://docs.x.com/x-api/media/upload-media
- **X create post**: https://docs.x.com/x-api/posts/create-post
- **UFC events**: https://www.ufc.com/events

## How It Works

1. Fetches all markets for the specified UFC event from Gamma API
2. Extracts the `YYYY-MM-DD` suffix from each Polymarket UFC fight slug
3. Matches that date to the official event page listed at `ufc.com/events`
4. Extracts and caches the event page's 1x desktop hero image under `data/ufc_event_images/`
5. Extracts all `clobTokenIds` (one per outcome per market)
6. Opens WebSocket connection to `wss://ws-subscriptions-clob.polymarket.com/ws/market`
7. Subscribes to the `market` channel with all token IDs
8. Listens for `last_trade_price` events containing:
   - `asset_id`: Token being traded
   - `size`: Number of shares traded
   - `price`: Trade price (0-1)
   - `side`: BUY or SELL
9. Calculates USD value (`size * price`) and alerts if above threshold

## Output

- Console logs all activity
- Saves all trades to `logs/ufc_<event_slug>.log`
- Sends a Pushover notification with the Polymarket link for large wagers
- Posts a URL-free X alert with the matching UFC card image using OAuth 1.0a user context
- Falls back to one URL-free text-only X post if UFC discovery, image download, or X media upload fails
- Skips X posts when the bet price is already displayed as 100%, while still sending the Pushover alert

## Notes

- Alerts rely on `last_trade_price` (executed trades). `price_change` is emitted when orders are placed or canceled, so it can create false whale alerts if used for detection. See the Market Channel docs for details: https://docs.polymarket.com/developers/CLOB/websocket/market-channel.md
- Only BUY side triggers alerts (avoids duplicate notifications)
- X alert format mirrors the Pushover details with a compact one-line double-rule header designed to stay clean on phone screens: `═════ 🐳 UFC SHARP ACTION ═════`
- The Polymarket URL remains in Pushover but is deliberately omitted from X
- The same cached card image is used for every fight notification from that card
- X posting failures are logged and do not stop Pushover alerts or the monitor loop
- Supports both exact event slug and keyword search
- Auto-reconnects on WebSocket disconnection
