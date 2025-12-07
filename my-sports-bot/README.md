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

### 3. `monitor_game_holders.py`

- Monitors **changes in holdings** for NFL game markets over time using `/holders`.
- Maintains a snapshot in `data/nfl_holders_snapshot.csv` and, on each run, compares the latest snapshot against the previous one.
- When a wallet’s position value on a given game/outcome **crosses $10,000 USD** (based on current outcome price), logs a large-holder event to `data/large_wagers_events.csv` and prints a `LARGE HOLDER:` line.

### 4. `list_top_game_holders.py`

- Fetches holders for all NFL **moneyline** game markets using the Data API `/holders` endpoint.
- Aggregates them into a single table and prints the **top 50 holders across all games/sides**, showing:
  - Approximate USD size of the position
  - Holder identity (name/pseudonym/wallet)
  - Wallet address
  - Team/outcome and game slug.