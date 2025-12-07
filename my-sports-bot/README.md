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

### 3. `get_nfl_game_bets.py`

- Pulls recent fills (bets) for NFL game markets using the Gamma `/fills` endpoint.
- Single-game mode: `python get_nfl_game_bets.py --game-id <market_id>` saves fills for one market.
- Batch mode: `python get_nfl_game_bets.py --all` mirrors the `get_nfl_games.py` filters and saves fills for every active game market.
- Optional `--notify` flag (batch mode) sends a Pushover alert when it detects newly seen action over $10,000 on any tracked market—either a single fill or a set of new fills from the same actor/outcome that collectively cross the threshold. Intended for cron use on a server.
- References: Polymarket Gamma REST docs for market discovery and fills (`https://docs.polymarket.com/#fills`, `https://docs.polymarket.com/#markets`).
