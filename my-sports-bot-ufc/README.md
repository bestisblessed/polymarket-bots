# UFC Whale Monitor Bot

Real-time monitoring of Polymarket UFC fight markets for whale activity using the CLOB WebSocket API.

## Workflow Overview

This bot uses the most efficient approach for whale detection:

1. **Market Discovery** (Gamma API) - Fetches all markets for a UFC event
2. **Real-time Monitoring** (CLOB WebSocket) - Subscribes to `last_trade_price` events to detect executed trades
3. **UFC Card Art** (UFC.com) - Matches each fight date to the official upcoming event page and caches its desktop hero image
4. **Alert System** (Pushover + X) - Sends linked Pushover notifications and URL-free X posts with the matching card image
5. **Trader Attribution** (public Data API) - Matches each X alert to a unique BUY trade, then adds the public trader name/wallet and a profile QR footer

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

Install the repository requirements in your deployment's virtual environment.
The profile footer uses `qrcode[pil]==8.2` (Pillow 10.1 or newer); no global
installation is required. If QR rendering is unavailable, the alert retains
its trader text and original artwork.

## API References

- **Gamma API (markets)**: https://docs.polymarket.com/api-reference/core/get-market
- **WebSocket Overview**: https://docs.polymarket.com/developers/CLOB/websocket/wss-overview
- **Market Channel**: https://docs.polymarket.com/developers/CLOB/websocket/market-channel
- **X media upload**: https://docs.x.com/x-api/media/upload-media
- **X create post**: https://docs.x.com/x-api/posts/create-post
- **UFC events**: https://www.ufc.com/events
- **Public trade data**: https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets
- **Current market stream fields**: https://docs.polymarket.com/market-data/realtime-data
- **QR generation**: https://github.com/lincolnloop/python-qrcode
- **X character counting**: https://docs.x.com/fundamentals/counting-characters
- **X pricing**: https://docs.x.com/x-api/getting-started/pricing

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
- X alert format uses the header `🐳 UFC SHARP ACTION`, followed by wager details and a blank line before trader attribution
- The Polymarket URL remains in Pushover but is deliberately omitted from X
- The same cached card artwork is reused unchanged; QR footers are currently disabled
- X posting failures are logged and do not stop Pushover alerts or the monitor loop
- Supports both exact event slug and keyword search
- Auto-reconnects on WebSocket disconnection

## Trader matching and profile footer

For eligible X alerts, the bot waits up to 15 seconds for public `/trades`
indexing. The query uses the market condition ID, BUY/taker trades, and a
two-second window around the WebSocket timestamp. Matching requires the same
condition ID, token, side, price (within 0.000001), size (within 0.0001 shares),
and timestamp (within two seconds). If the stream supplies `transaction_hash`,
it must match the public trade's transaction hash. Otherwise only one distinct
matching trade is accepted. This is correlation, not proof of a person's real
identity; split fills, ambiguous results, malformed rows, saturated query
windows, and unavailable data fall back to the existing unattributed alert.

The public label uses name, pseudonym, then wallet. URL-like names and X
mentions are rejected. After a blank line, the tweet appends
`Polymarket Trader: <name> | Wallet: <full-wallet>`. Descriptive labels are
shortened as needed to reserve the numeric wager and trader/wallet line under
X's weighted 280-character limit.

QR composition is currently **commented out** in both `process_last_trade_price`
and `dry_run_fixture`. Posts and dry runs use the original artwork. To restore
the footer, uncomment the marked `image_path = compose_trader_image(...)`
assignment in both functions. The helper and its dependencies remain available.
The verification bundle's QR screenshots and live post document the earlier
QR-enabled version, not the currently disabled behavior.

When re-enabled, the entire artwork is preserved above a white footer. Black-on-white QR codes
use medium error correction and a four-module quiet zone. Composed files under
`data/trader_profile_images/` are cached by artwork version, wallet and name,
so a different wallet never inherits another trader's QR. Images remain below
5 MB; rendering errors fall back to the original image.

X currently lists $0.015 for ordinary posts and $0.20 for URL-containing posts.
When re-enabled, the profile URL appears only in image pixels, never tweet text. QR-in-image
billing is not explicitly guaranteed by X; confirm the actual account charge
before treating this as a billing guarantee.

## Dry-run verification

```bash
python -m unittest discover -s my-sports-bot-ufc -p 'test_trader_attribution.py' -v
python my-sports-bot-ufc/monitor_ufc_large_wagers.py --dry-run \
  --trade-fixture /path/to/trade-fixture.json --output-dir /path/to/preview
```

A fixture contains `event` (raw `last_trade_price` fields), `market_info`
(`condition_id`, `event_title`, `outcome`, optional `market_display` and
`ufc_image_path`, relative to the fixture or absolute), and `trades` (public Data API rows). Optional `provenance`
records whether the WebSocket event was captured or reconstructed; optional
`post_prefix` labels historical test samples. All identifiers must come from
the matching record, not illustrative screenshot examples.

Dry runs emit `tweet.txt` and `evidence.json`, referencing the original image
while QR composition is disabled. They need
no X/Pushover credentials or threshold configuration and perform no API reads,
notifications, uploads, or health-check writes. Production posting still uses
the existing OAuth and media-upload path, with no automatic POST retries.
