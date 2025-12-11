# Polymarket Bots

A collection of Python scripts for interacting with Polymarket's various APIs including Data API, CLOB API, and real-time WebSocket streams.

## Scripts Overview

---

- **`poly_data_get_user_balance.py`** - Gets total holdings value across all markets for a user wallet address

- **`poly_data_get_user_activity.py`** - Fetches and displays user activity (trades, buys, sells) from given wallet address with pagination support
	- Collected data is stored in timestamped JSON files under `./data/user-activity/`

- **`poly_data_get_user_positions.py`** - Gets current positions across all markets with P&L calculations for a user wallet
	- Collected data is stored in timestamped JSON files under `./data/user-positions/`

- **`poly_data_get_event_markets_and_holders.py`** - Lists all markets info from a given event slug with the top holders of each market

- **`poly_data_get_user_positions_v1.py`** - Gets current positions across all markets for a user wallet using raw API requests

- **`poly_data_get_user_positions_v2.py`** - Gets current positions across all markets for a user wallet using with P&L calculations and risk management data

- **`poly_gamma_list_markets.py`** - Lists all markets using with detailed market metadata and filtering options

- **`poly_gamma_list_markets_by_category.py`** - Lists markets filtered by category (Politics, Finance, Crypto, Sports, Tech) using the Gamma API

- **`poly_gamma_list_markets_by_volume.py`** - Lists top 50 markets sorted by trading volume using the Gamma API client

- **`my-creamster-monitor-bot/monitor_creamster_wallet.py`** - Minimal cron-friendly watcher that pings Pushover when AltCreamster's wallet has fresh activity via the Polymarket Data API activity endpoint
