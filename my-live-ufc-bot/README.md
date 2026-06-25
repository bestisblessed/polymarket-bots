# Live UFC 99/1 Odds Bot

Notification-only Polymarket UFC moneyline monitor. It watches live CLOB top-of-book prices and sends a Pushover alert when a fighter can be bought at `0.01` or lower while Polymarket's sports feed says that exact fight is live.

This bot does not place bets.

## Why this method

- Gamma `/events` discovers active UFC events and their moneyline token IDs.
- CLOB `/books` seeds the current best bid/ask before the websocket starts.
- CLOB market websocket streams live `best_bid_ask` updates with `custom_feature_enabled: true`.
- Sports websocket gates alerts to fights with a live `sport_result` and suppresses fights marked ended.
- CLOB `market_resolved` events suppress alerts for already-resolved markets.
- The alert uses the best ask, because that is the price you could pay to buy the low-probability fighter.

References:

- https://docs.polymarket.com/developers/gamma-markets-api/gamma-structure
- https://docs.polymarket.com/trading/orderbook
- https://docs.polymarket.com/developers/CLOB/websocket/market-channel-migration-guide
- https://docs.polymarket.com/market-data/websocket/sports

## Setup

Copy or create `.env` in this directory:

```bash
cp env.example .env
```

Required for notifications:

```bash
PUSHOVER_API_TOKEN=...
PUSHOVER_GROUP_KEY=...
```

Optional settings:

```bash
UFC_LIVE_ALERT_PRICE=0.01
UFC_LIVE_ALERT_TITLE=UFC 99/1 Live Odds
UFC_LIVE_HEARTBEAT_SECONDS=300
UFC_REQUIRE_SPORTS_LIVE=true
```

## Usage

```bash
./run.sh
./run.sh all
./run.sh ufc-son-dei-2026-05-30
./run.sh "song figueiredo"
```

Useful checks:

```bash
python monitor_live_ufc_odds.py --list
python monitor_live_ufc_odds.py all --no-notify --seed-only
python monitor_live_ufc_odds.py all --no-notify --max-seconds 30
UFC_LIVE_ALERT_PRICE=1.00 python monitor_live_ufc_odds.py all --no-notify --seed-only --unsafe-ignore-live-gate
```

## Alert behavior

- Watches UFC moneyline markets only.
- Triggers when a fighter's best ask is at or below `UFC_LIVE_ALERT_PRICE`.
- By default, suppresses alerts until the sports websocket reports that exact fight slug as live.
- Suppresses alerts after the sports websocket says the fight ended or the CLOB websocket sends `market_resolved`.
- Sends one alert per fighter token per bot run.
- Logs triggered alerts to `logs/alerts.log`.
- Prints alerts instead of sending Pushover when `--no-notify` is used.
