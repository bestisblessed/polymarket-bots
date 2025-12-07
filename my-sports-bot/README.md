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

### 4. `list_top_game_holders.py`

- Lists **top 50 holders by position value** across all NFL moneyline markets.
- Uses Data API `/holders` endpoint.
- Shows: USD position size, holder identity, wallet, team/outcome, game.
  - Approximate USD size of the position
  - Holder identity (name/pseudonym/wallet)
  - Wallet address
  - Team/outcome and game slug.

### 5. `list_top_game_holders_profit.py`

- Lists **top 50 holders by potential profit** across all NFL moneyline markets.
- Formula: `potential_profit = shares * (1 - price)`
- Highlights sharp underdog bets that would pay big if they win.
- Shows: USD potential profit, holder identity, wallet, team/outcome, game.
  - Approximate USD potential profit
  - Holder identity (name/pseudonym/wallet)
  - Wallet address
  - Team/outcome and game slug.

### 5. `monitor_game_holders.py`

- Monitors holdings and sends **Pushover alerts** when a wallet crosses **$10,000 position value**.
- Logs events: `data/large_wagers_events.csv`

### 6. `monitor_game_holders_profit.py`

- Monitors holdings and sends **Pushover alerts** when a wallet crosses **$20,000 potential profit**.
- Catches sharp underdog bets (e.g., $5K on a 20% underdog = $20K potential profit).
- Logs events: `data/large_profit_events.csv`