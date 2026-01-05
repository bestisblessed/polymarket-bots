# Polymarket Bots

A collection of Python scripts for interacting with Polymarket's various APIs including Data API, CLOB API, and real-time WebSocket streams.

# Bots (Production)

- **`my-openai-whale-bot`** - Monitors a fixed list of whale wallets and sends Pushover alerts for new trades.
	- Pulls recent activity for each wallet and filters for BUY/SELL events.
	- Run via `bash my-openai-whale-bot/run.sh` with a local `.env` containing `PUSHOVER_API_TOKEN` and `PUSHOVER_GROUP_KEY`.

- **`my-sports-bot`** - NFL market and holder tracking with alerting.
	- Fetches NFL markets/games and lists top holders using the Data API.
	- Monitors large positions or potential profit and sends Pushover alerts.
	- Cron helpers: `my-sports-bot/run_monitor_game_holders.sh` and `my-sports-bot/run_monitor_game_holders_profit.sh`.

- **`my-creamster-monitor-bot`** - Watches a single wallet and pings Pushover on new activity.
	- Calls the Polymarket Data API activity endpoint for the AltCreamster wallet.
	- Run via `bash my-creamster-monitor-bot/run.sh` with local `.env` credentials.

# Bots (Development)

- **Market screener bot** - Discover new opportunities quickly.
	- Finds new markets by category/liquidity; scores them by volume/OI; outputs a ranked watchlist and sends alerts for new markets.
	- Uses: `Gamma` (direct REST or `PolymarketGammaClient`), maybe GraphQL.

- **Directional trading bot** - Model-driven entries and exits.
	- Compute fair value and place trades when mispricings appear.
	- Enforce position sizing, stop-loss, and exposure limits.
	- Uses: `PolymarketGammaClient` + `PolymarketClobClient` (+ WebSockets for fills).

- **Market-making / liquidity provision** - Quote both sides and earn spread.
	- Streams orderbook updates, keeps quotes around mid, manages inventory, and cancels/replaces orders on fills to provide consistent liquidity and earn the spread.
	- Uses: `PolymarketGammaClient` + `PolymarketClobClient` + `PolymarketWebsocketsClient`.

- **PnL / risk monitor** - Portfolio health and risk alerts.
	- Periodically pulls positions & PnL, applies risk limits, possibly triggers hedges when thresholds are breached.
	- Uses: `PolymarketDataClient` + GraphQL subgraphs.

- **Copy-trading bot** - Mirror top wallets with controls.
	- Track selected wallets and mirror trades with caps and delays.
	- Add safety checks for slippage, liquidity, and market limits.
	- Uses: `PolymarketDataClient` for leaderboards/holders, `PolymarketClobClient` for mirroring trades.


## Scripts Overview (utils)

General-purpose helpers in `utils/`:

- **`utils/poly_data_get_user_balance.py`** - Gets total holdings value across all markets for a user wallet address.
- **`utils/poly_data_get_user_activity.py`** - Fetches user activity with pagination.
	- Writes timestamped JSON under `data/user-activity/`.
- **`utils/poly_data_get_event_markets_and_holders.py`** - Lists markets for an event slug with top holders.
- **`utils/poly_data_get_user_positions_v1.py`** - Current positions using raw API requests.
- **`utils/poly_data_get_user_positions_v2.py`** - Current positions with P&L and risk metadata.
- **`utils/poly_gamma_list_markets.py`** - Lists markets with detailed metadata and filters.
- **`utils/poly_gamma_list_markets_by_category.py`** - Lists markets filtered by category.
- **`utils/poly_gamma_list_markets_by_volume.py`** - Lists top markets by trading volume.
