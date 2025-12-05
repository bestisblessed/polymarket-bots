# Polymarket Bots

A collection of Python scripts for interacting with Polymarket's various APIs including Data API, CLOB API, and real-time WebSocket streams.

## Scripts Overview

1. **`poly_data_get_user_balance.py`** - Gets total holdings value across all markets for a user wallet address

--- 

2. **`poly_data_get_user_activity.py`** - Fetches and displays user activity (trades, buys, sells) from given wallet address with pagination support
- Collected data is stored in timestamped JSON files under `./data/user-activity/`

---

3. **`poly_data_get_user_positions.py`** - Gets current positions across all markets with P&L calculations for a user wallet
- Collected data is stored in timestamped JSON files under `./data/user-positions/`

---

4. **`poly_data_get_event_markets_and_holders.py`** - Lists all markets info from a given event slug with the top holders of each market

---

5. **`poly_gamma_list_markets_by_volume.py`** - Lists top 50 markets sorted by trading volume using the Gamma API client
