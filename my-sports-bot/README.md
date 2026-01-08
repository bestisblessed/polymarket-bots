# NFL Sports Bot

A collection of scripts for monitoring NFL prediction markets on Polymarket, tracking large wagers, and analyzing betting patterns

---

## Data Collection Scripts

### 1. `get_nfl_markets.py`

- Fetches all active NFL prediction markets from Polymarket.
- Uses Gamma API `/events` endpoint with NFL tag ID `10`
- Data includes:
  - **Market basics:** id, slug, question, description, outcomes, outcomePrices
  - **Pricing:** bestAsk, bestBid, lastTradePrice, spread, competitive
  - **Volume:** volume, volume24hr, volume1wk, volume1mo, volume1yr, volumeClob
  - **Liquidity:** liquidity, liquidityClob, liquidityNum
  - **Trading:** acceptingOrders, enableOrderBook, orderMinSize, orderPriceMinTickSize
  - **Event info:** event_title, event_slug (added by script)

### 2. `get_nfl_games.py`

- Fetches NFL game markets (spreads, totals, moneylines) for upcoming games from Polymarket.
- Uses Gamma API `/markets` endpoint with NFL game tag ID `100639`
- Data includes:
  - **Market basics:** id, slug, question, description, outcomes, outcomePrices
  - **Pricing:** bestAsk, bestBid, lastTradePrice, spread, competitive
  - **Volume:** volume, volume24hr, volume1wk, volume1mo, volume1yr, volumeClob
  - **Liquidity:** liquidity, liquidityClob, liquidityNum
  - **Game-specific:** sportsMarketType, gameStartTime, events (with game details)
  - **Status:** active, closed, approved, archived, featured, new
  - **Trading:** acceptingOrders, enableOrderBook, orderMinSize, orderPriceMinTickSize
  - **Price changes:** oneDayPriceChange, oneWeekPriceChange

### 3. `get_nfl_game_bets.py`

- Pulls **historical transaction data** (fills/bets) for NFL game markets using the Data API `/trades` endpoint.
- **Unique capability:** Unlike other scripts that show current market state or holder positions, this script shows **actual bets that were placed** — when they occurred, by whom, and for how much.
- **Important:** This script only shows **executed trades (fills)**, not pending orders. If someone places a limit order that hasn't been filled yet, it won't appear until the order actually executes. Each entry includes the execution price, size, timestamp, and transaction hash.
- **Single-game mode:** `python get_nfl_game_bets.py --game-id <market_id>` saves fills for one market.
- **Batch mode:** `python get_nfl_game_bets.py --all` mirrors the `get_nfl_games.py` filters and saves fills for every active game market.
- **Notification mode:** `--notify` flag (batch mode) sends Pushover alerts when it detects newly seen betting activity over $10,000 on any tracked market. Alerts trigger when:
  - A single fill exceeds $10,000, OR
  - Multiple fills from the same actor/outcome collectively cross $10,000 in one run, OR
  - Cumulative totals across multiple runs finally push the running total over $10,000
- **State management:** Persists seen fill IDs and cumulative totals in `data/last_fill_state.json` to prevent duplicate alerts and track accumulation over time.
- **API usage:** 
  - `data-api.polymarket.com/trades` (unique endpoint — no other script uses this)
  - `gamma-api.polymarket.com/markets` (for market metadata)
- **Use cases:** Analyze betting patterns, track large bettor activity over time, monitor when big bets are placed (not just current holdings).

---

## Analysis Scripts

### 4. `list_top_game_holders.py`

- Lists **top 50 holders by position value** across all NFL moneyline markets.
- Uses Data API `/holders` endpoint to get current positions.
- Shows: USD position size, holder identity, wallet, team/outcome, game.
  - Approximate USD size of the position
  - Holder identity (name/pseudonym/wallet)
  - Wallet address
  - Team/outcome and game slug.

### 5. `list_top_game_holders_profit.py`

- Lists **top 50 holders by potential profit** across all NFL moneyline markets.
- Formula: `potential_profit = shares * (1 - price)`
- Highlights sharp underdog bets that would pay big if they win.
- Uses Data API `/holders` endpoint to get current positions.
- Shows: USD potential profit, holder identity, wallet, team/outcome, game.
  - Approximate USD potential profit
  - Holder identity (name/pseudonym/wallet)
  - Wallet address
  - Team/outcome and game slug.

---

## Monitoring Scripts

### 0. Recommended: `nfl_whale_service.py` (single-service mode)

- **Best way to run everything together**: one always-on process (ideal for `systemd` on a Raspberry Pi).
- Runs the three monitoring approaches in one place:
  - **Order book (real-time)**: uses the **CLOB WebSocket** to detect large pending orders (reuses `monitor_pending_orders.py`)
  - **Trades (polling)**: polls the Data API `/trades` endpoint for executed fills (reuses `get_nfl_game_bets.py`)
  - **Holders + profit (polling)**: polls the Data API `/holders` endpoint to detect snapshot deltas (reuses `monitor_game_holders*.py`)
- **Why it isn’t “all realtime”**: Polymarket’s public WebSocket is for CLOB market data (orderbook/price updates). Trades/holders come from the Data API (REST), so those remain polling-based. See official base URLs here: `https://docs.polymarket.com/quickstart/reference/endpoints`.
- **Run locally**: `python nfl_whale_service.py`
- **Intervals (optional env vars)**:
  - `NFL_TRADES_INTERVAL_S` (default 180)
  - `NFL_HOLDERS_INTERVAL_S` (default 300)
  - `NFL_PROFIT_INTERVAL_S` (default 480)

### 6. `monitor_game_holders.py`

- **Snapshot-based monitoring:** Takes periodic snapshots of current holder positions and compares them.
- Sends **Pushover alerts** when a wallet's position value crosses **$10,000** between snapshots.
- **How it works:**
  1. Fetches current positions from `data-api.polymarket.com/holders`
  2. Compares current snapshot vs previous snapshot (saved in `data/nfl_holders_snapshot.csv`)
  3. Detects when: `prev_position_value < $10,000 <= curr_position_value`
  4. Alerts on position value changes, not individual bets
- **Limitations:** Only detects when total position crosses threshold between runs; may miss accumulation of smaller bets.
- Logs events: `data/large_wagers_events.csv`

### 7. `monitor_game_holders_profit.py`

- **Snapshot-based monitoring:** Takes periodic snapshots of current holder positions and compares potential profit.
- Sends **Pushover alerts** when a wallet's potential profit crosses **$20,000** between snapshots.
- **How it works:**
  1. Fetches current positions from `data-api.polymarket.com/holders`
  2. Calculates potential profit: `shares * (1 - price)` for each position
  3. Compares current snapshot vs previous snapshot (saved in `data/nfl_holders_profit_snapshot.csv`)
  4. Detects when: `prev_potential_profit < $20,000 <= curr_potential_profit`
  5. Catches sharp underdog bets (e.g., $5K on a 20% underdog = $20K potential profit)
- **Limitations:** Only detects when total potential profit crosses threshold between runs.
- Logs events: `data/large_profit_events.csv`

### 8. `monitor_pending_orders.py`

- **Order book-based monitoring:** Monitors the CLOB (Central Limit Order Book) for active pending orders in real-time.
- Sends **Pushover alerts** when a pending order exceeds **$10,000**.
- **How it works:**
  1. Fetches active orders from `clob.polymarket.com` order book API
  2. Checks both buy orders (bids) and sell orders (asks)
  3. Calculates order value: `price * size`
  4. Detects when: `order_value >= $10,000`
  5. Tracks seen order IDs in `data/pending_orders_state.json` to prevent duplicate alerts
- **Advantages:** 
  - **Early detection:** See orders as soon as they're placed, before execution
  - **Intent signals:** Shows what price whales are willing to pay
  - **Real-time:** Faster than waiting for fills to execute
  - **Market impact:** Large pending orders can move markets even before they fill
- **Batch mode:** `python monitor_pending_orders.py` monitors all NFL game markets
- **Single-game mode:** `python monitor_pending_orders.py --game-id <market_id>` monitors one market
- **API usage:** `clob.polymarket.com` (order book endpoint)

---

## Monitoring Approaches: Snapshot vs Transaction vs Order Book-Based

This bot uses **three different monitoring approaches** that complement each other:

### Snapshot-Based Monitoring (`monitor_game_holders*.py`)

- **Data source:** Current positions (`data-api.polymarket.com/holders`)
- **Detection method:** Compares position snapshots between runs
- **What it catches:** Large position value changes
- **Timing:** Detects when position crosses threshold between snapshot intervals
- **Best for:** Monitoring overall position growth, catching large position changes

**Example:** If someone's position grows from $8K to $12K between runs, it alerts.

### Transaction-Based Monitoring (`get_nfl_game_bets.py --notify`)

- **Data source:** Historical transactions (`data-api.polymarket.com/trades`)
- **Detection method:** Tracks individual fills/bets and accumulates totals
- **What it catches:** Actual betting activity, accumulation of smaller bets
- **Timing:** Detects when cumulative fills cross threshold (works across multiple runs)
- **Best for:** Tracking actual betting patterns, catching accumulation of smaller bets over time

**Example:** If someone places 5 bets of $2K each, it tracks each one and alerts when cumulative reaches $10K.

### Order Book-Based Monitoring (`monitor_pending_orders.py`) ⭐ **Most Proactive**

- **Data source:** Active orders (`clob.polymarket.com` order book)
- **Detection method:** Monitors pending orders in real-time
- **What it catches:** Large orders as soon as they're placed (before execution)
- **Timing:** Real-time detection when orders appear in order book
- **Best for:** Early whale detection, seeing intent signals, catching orders before they execute

**Example:** If someone places a $15K limit order, it alerts immediately (even if it hasn't filled yet).

### When to Use Which

- **Use snapshot-based** (`monitor_game_holders*.py`) when you want to know about large position changes or overall position growth.
- **Use transaction-based** (`get_nfl_game_bets.py --notify`) when you want to track actual betting activity and catch accumulation of smaller bets.
- **Use order book-based** (`monitor_pending_orders.py`) when you want **early detection** and to see what prices whales are targeting before orders execute.

**For whale monitoring, order book-based is the most proactive** — you see activity as soon as orders are placed, not after they execute. All three approaches can be run simultaneously for comprehensive monitoring.

---

## API Endpoints Used


| Script                      | Endpoint                           | Purpose                            |
| --------------------------- | ---------------------------------- | ---------------------------------- |
| `get_nfl_markets.py`        | `gamma-api.polymarket.com/events`  | Market discovery                   |
| `get_nfl_games.py`          | `gamma-api.polymarket.com/markets` | Game market metadata               |
| `get_nfl_game_bets.py`      | `data-api.polymarket.com/trades`   | Historical transaction data        |
| `get_nfl_game_bets.py`      | `gamma-api.polymarket.com/markets` | Market metadata                    |
| `monitor_pending_orders.py` | `clob.polymarket.com`              | Active pending orders (order book) |
| `monitor_pending_orders.py` | `gamma-api.polymarket.com/markets` | Market metadata                    |
| `nfl_whale_service.py`      | `ws-subscriptions-clob.polymarket.com` | Real-time orderbook (WebSocket) |
| `nfl_whale_service.py`      | `data-api.polymarket.com`          | Trades + holders polling           |
| `list_top_game_holders*.py` | `data-api.polymarket.com/holders`  | Current positions                  |
| `monitor_game_holders*.py`  | `data-api.polymarket.com/holders`  | Current positions                  |


---

## References

- Polymarket Gamma REST API: `https://docs.polymarket.com`
- Market discovery: `https://docs.polymarket.com/#markets`
- Fills/trades: `https://docs.polymarket.com/#fills.`

## Running as a single service (systemd on Raspberry Pi)

1. Ensure `.env` contains:
   - `PUSHOVER_API_TOKEN=...`
   - `PUSHOVER_GROUP_KEY=...`
   - Optional: `NFL_FILL_THRESHOLD_USD=10000`
2. Copy the unit template from `deploy/polymarket-nfl-whale.service` to:
   - `/etc/systemd/system/polymarket-nfl-whale.service`
3. Enable + start:
   - `sudo systemctl daemon-reload`
   - `sudo systemctl enable polymarket-nfl-whale`
   - `sudo systemctl start polymarket-nfl-whale`
4. Tail logs:
   - `journalctl -u polymarket-nfl-whale -f`

With this setup, cron only needs to refresh games (e.g. weekly `get_nfl_games.py`). The service runs the monitoring continuously.
