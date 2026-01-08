# NFL Sports Bot

--- 

## Scripts

### Required run order

The holders and monitoring scripts require `data/nfl_games.json`, which is created by
`get_nfl_games.py`. Always run `get_nfl_games.py` before running any of the scripts
that read NFL game data from disk.

### Minimal workflow (recommended order)

1. **Fetch latest NFL game markets** (required data file):
   - `python get_nfl_games.py`
2. **Choose what you want to do next** (optional, based on your goal):
   - **List top holders**: `python list_top_game_holders.py`
   - **List top holders by potential profit**: `python list_top_game_holders_profit.py`
   - **Monitor large wagers** (requires `.env` with Pushover keys):
     - One-off run: `python monitor_game_holders.py`
     - Cron runner: `bash run_monitor_game_holders.sh`
   - **Monitor large profit positions** (requires `.env` with Pushover keys):
     - One-off run: `python monitor_game_holders_profit.py`
     - Cron runner: `bash run_monitor_game_holders_profit.sh`

### Compare & contrast (and when to use each)

#### `get_nfl_markets.py` vs `get_nfl_games.py`

| Aspect | `get_nfl_markets.py` | `get_nfl_games.py` |
| --- | --- | --- |
| Purpose | All active NFL prediction markets across all NFL event types. | NFL game markets (spreads, totals, moneyline) for upcoming games. |
| API endpoint | `GET /events` (tag `10`) | `GET /markets` (tag `100639`) |
| Output files | `data/nfl_markets.json`, `data/nfl_markets.csv` | `data/nfl_games.json`, `data/nfl_games.csv` |
| Typical use | Broad NFL market discovery. | Game-specific betting workflows and holder/monitor scripts. |
| Required by other scripts | No. | Yes: required by holder/monitor scripts. |

**Do you need both?**  
- If you only run the holder/monitor scripts, you only need `get_nfl_games.py`.  
- Use `get_nfl_markets.py` when you want *all* NFL markets beyond game lines.

#### `list_top_game_holders.py` vs `list_top_game_holders_profit.py`

| Aspect | `list_top_game_holders.py` | `list_top_game_holders_profit.py` |
| --- | --- | --- |
| Ranking metric | Position value (USD, `shares * price`). | Potential profit (`shares * (1 - price)`). |
| Highlights | Biggest raw positions. | Biggest underdog payoff opportunities. |
| Output | Prints top 50 holders by position size. | Prints top 50 holders by potential profit. |
| Data dependency | `data/nfl_games.json` | `data/nfl_games.json` |

**Do you need both?**  
- Use the **position value** list to see who has the most money on the board.  
- Use the **potential profit** list to see who stands to win the most if longshots hit.  

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
