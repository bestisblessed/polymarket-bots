# NFL Sports Bot

--- 

## Scripts

### 1. `get_nfl_markets.py`

- Fetches all active NFL prediction markets from Polymarket.
- Uses `/events` endpoint with NFL tag ID `10`
- Data includes:
  - **Market basics:** id, slug, question, description, outcomes, outcomePrices
  - **Pricing:** bestAsk, bestBid, lastTradePrice, spread, competitive
  - **Volume:** volume, volume24hr, volume1wk, volume1mo, volume1yr, volumeClob
  - **Liquidity:** liquidity, liquidityClob, liquidityNum
  - **Trading:** acceptingOrders, enableOrderBook, orderMinSize, orderPriceMinTickSize
  - **Event info:** event_title, event_slug (added by script)

### 2. `get_nfl_games.py`

- Fetches NFL game markets (spreads, totals, moneylines) for upcoming games from Polymarket.
- Uses `/markets` endpoint with NFL game tag ID `100639`
- Data includes:
  - **Market basics:** id, slug, question, description, outcomes, outcomePrices
  - **Pricing:** bestAsk, bestBid, lastTradePrice, spread, competitive
  - **Volume:** volume, volume24hr, volume1wk, volume1mo, volume1yr, volumeClob
  - **Liquidity:** liquidity, liquidityClob, liquidityNum
  - **Game-specific:** sportsMarketType, gameStartTime, events (with game details)
  - **Status:** active, closed, approved, archived, featured, new
  - **Trading:** acceptingOrders, enableOrderBook, orderMinSize, orderPriceMinTickSize
  - **Price changes:** oneDayPriceChange, oneWeekPriceChange

### 3. `get_nfl_game_bets_single.py`

- Loads the latest `data/nfl_games.json` output and fetches all trades for one game (slug or event id) via the `/trades` endpoint in the [Polymarket Data API](https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets).
- Saves a JSON report at `data/game-bets/<slug>.json` containing the raw trades plus a quick summary (count + USDC total).
- Usage: `python3 get_nfl_game_bets_single.py nfl-sea-atl-2025-12-07` (omit the slug to use the first game in the file).
- The request loops with `offset` pagination, so if you only see ~500 fills that is all the API currently returns for that market (the docs allow up to 10k rows per request when available).

### 4. `get_nfl_game_bets_all.py`

- Iterates through every game stored in `data/nfl_games.json`, hits the same `/trades` Data API endpoint, and emits one report per game under `data/game-bets/`.
- Prints a concise line per slug so you can monitor progress and total USDC per matchup while it runs.
- Usage: `python3 get_nfl_game_bets_all.py` (ensure `get_nfl_games.py` was run recently so the input list is current).

### 5. `get_nfl_game_holders.py`

- Targets the [Get top holders for markets](https://docs.polymarket.com/api-reference/core/get-top-holders-for-markets) endpoint to capture the largest positions per outcome for every NFL moneyline market.
- Builds `data/game-holders/<slug>.json` snapshots that include each holder’s display name / wallet, outcome, share count, and an approximate USDC value using the latest outcome prices in `data/nfl_games.json`.
- Usage: `python3 get_nfl_game_holders.py` (tune the `LIMIT` / `MIN_BALANCE` constants near the top if you want deeper or shallower lists).
- To detect new large wagers, schedule this script via cron (e.g., every 5 minutes), persist each run, and diff successive files: if a holder’s `shares` delta * current price exceeds your alert threshold, trigger a notification. This avoids replaying the entire trade history while still surfacing whales as soon as their net exposure changes.
