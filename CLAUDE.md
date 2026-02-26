# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Collection of Python/JavaScript bots and utilities for Polymarket prediction markets. Focuses on whale monitoring, sports betting analytics, and automated alerts via Pushover notifications.

## Development Commands

No build step. Run scripts directly with Python:

```bash
# Install dependencies
pip install -r requirements.txt

# Utility scripts
python utils/poly_data_get_user_balance.py 0xWallet
python utils/poly_gamma_list_markets.py

# Bot scripts
python my-sports-bot/get_nfl_markets.py
python my-sports-bot-ufc/monitor_ufc_large_wagers.py "fighter names"

# Via cron runners
bash my-openai-whale-bot/run.sh
bash my-sports-bot/run_monitor_game_holders.sh

# UFC monitoring
./my-sports-bot-ufc/run_ufc_monitor.sh           # All active fights
./my-sports-bot-ufc/run_ufc_monitor.sh <slug>    # Specific event

# NFL unified service (daemon)
python my-sports-bot/nfl_whale_service.py
```

**Testing:** No test framework. Validate changes by running affected scripts with small inputs or short polling windows.

## Architecture

### Directory Structure
- `utils/` - One-off API helper scripts (balance, positions, market listings)
- `my-*-bot/` - Self-contained bot workflows with configs, runners, data dirs
- `data/` - Runtime outputs (git-ignored)
- `logs/` - Bot log files

### Polymarket APIs
| API | Base URL | Purpose |
|-----|----------|---------|
| Gamma | `gamma-api.polymarket.com` | Market discovery, metadata |
| Data | `data-api.polymarket.com` | Positions, holders, trades, activity |
| CLOB | `clob.polymarket.com` | Order book, pending orders |
| WebSocket | `ws-subscriptions-clob.polymarket.com/ws/market` | Real-time market data |

### Monitoring Approaches
1. **Snapshot-based** (`monitor_game_holders*.py`) - Compares holder positions between polling runs
2. **Transaction-based** (`get_nfl_game_bets.py --notify`) - Tracks executed fills, accumulates totals
3. **Order book-based** (`monitor_pending_orders.py`) - Real-time WebSocket for pending orders

### Common Patterns
- **Deduplication**: JSONL files track processed transaction hashes to prevent duplicate alerts
- **Threshold detection**: USD value calculated as `price * size`, alerts when crossing configured threshold
- **Environment config**: Each bot reads `.env` from its directory for Pushover credentials
- **State persistence**: JSON/CSV files in `data/` directories track snapshots and seen IDs

## Key Environment Variables

```bash
# Pushover (required for notification bots)
PUSHOVER_API_TOKEN=...
PUSHOVER_GROUP_KEY=...

# Thresholds (optional)
NFL_FILL_THRESHOLD_USD=10000
NFL_PENDING_ORDER_THRESHOLD_USD=10000
THRESHOLD=50000  # UFC bot

# Polling intervals (optional)
NFL_TRADES_INTERVAL_S=180
NFL_HOLDERS_INTERVAL_S=300
NFL_PROFIT_INTERVAL_S=480
```

## Coding Guidelines

- Python 3.9+, 4-space indentation, snake_case filenames
- Scripts accept args via `sys.argv` or read from `.env`
- When adding/updating Polymarket API usage: consult official docs directly, use exact flags/code shown, cite reference links
- If a script changes materially, update the relevant README.md
