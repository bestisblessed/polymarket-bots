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

### 3. `get_game_bets_single.py`

- Fetches all open orders/bets for a single NFL game market from Polymarket.
- Uses CLOB API `/book` endpoint with token IDs from the market
- Usage: `python3 get_game_bets_single.py <MARKET_ID>`
- Data includes:
  - **Bet details:** market_id, market_slug, market_question, outcome, token_id
  - **Order info:** side (buy/sell), price, size, usd_amount
  - Saves to `data/bets_<slug>_<market_id>.json`
- Reference: [Polymarket CLOB REST API Documentation](https://docs.polymarket.com/clob-rest-api)

### 4. `get_game_bets_all.py`

- Fetches all open orders/bets for all NFL game markets from Polymarket.
- Loops through all games fetched by `get_nfl_games.py`
- Uses CLOB API `/book` endpoint with token IDs from each market
- Data includes:
  - **Bet details:** market_id, market_slug, market_question, outcome, token_id
  - **Order info:** side (buy/sell), price, size, usd_amount
  - Saves to `data/nfl_game_bets_all.json`
- Reference: [Polymarket CLOB REST API Documentation](https://docs.polymarket.com/clob-rest-api)
