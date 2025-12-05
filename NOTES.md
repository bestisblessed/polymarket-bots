# Endpoints

1. CLOB REST – https://clob.polymarket.com
    - Discover markets, orderbooks, prices
    - Fetch historical trades, price history
    - Place / cancel orders (with auth) (Polymarket Documentation)
    - Building a trading bot(placing/cancelling orders)
    - Pulling historical prices or trades at scale.

2. Data-API – https://data-api.polymarket.com
    - Value of a user’s holdings across all markets (`/value`)
    - On-chain user activity (`/activity`)
    - Top holders for a token (`/holders`)
    - Top holders for a token (`/holders`)
    - Other user/account-centric endpoints ([Polymarket Documentation][5])
    - Portfolio dashboards
    - PnL / value tracking
    - Whale-tracking / holder analysis

3. CLOB WebSocket – wss://ws-subscriptions-clob.polymarket.com/ws/
    -  Market channel: public L2 book, price changes, last trade price, etc.
    -  User channel: your own order + trade updates (requires auth with API key/secret/passphrase).
    -  Near real-time prices for trading logic
    -  Reactive bots (cancel/replace orders immediately on fills)
    -  Live orderbook views

4. RTDS – wss://ws-live-data.polymarket.com
    - Crypto prices (`crypto_prices`, `crypto_prices_chainlink`)
    - Comments stream on Polymarket (new comments, reactions, replies)
    - Other RTDS feeds as they add them

***They provide an official TypeScript client, but you can hit the raw WS from Python similarly.***

---

# Summary:
1. `https://clob.polymarket.com` → trading + orderbook + historical prices (CLOB REST)
2. `https://data-api.polymarket.com` → user-centric + on-chain data (holdings, activity, holders)
3. `wss://ws-subscriptions-clob.polymarket.com/ws/` → real-time CLOB markets & user orders (CLOB WebSocket)
4. `wss://ws-live-data.polymarket.com` → real-time general streams (crypto prices, comments, etc.) (RTDS)

---

## Activity vs Positions Endpoints

**`/activity`** — Historical transactions
- Individual past transactions (trades, buys, sells)
- Each entry is a single transaction
- Includes transaction hash, timestamp, and transaction-level details
    **20 fields:**
    1. `proxyWallet`
    2. `timestamp`
    3. `conditionId`
    4. `type`
    5. `size`
    6. `usdcSize`
    7. `transactionHash`
    8. `price`
    9. `asset`
    10. `side`
    11. `outcomeIndex`
    12. `title`
    13. `slug`
    14. `icon`
    15. `eventSlug`
    16. `outcome`
    17. `name`
    18. `pseudonym`
    19. `bio`
    20. `profileImage`
    21. `profileImageOptimized`

**`/positions`** — Current holdings with P&L
- Current open positions across markets
- Each entry is an active position
- Includes calculated P&L, current value, and position metrics
    **25 fields:**
    1. `proxyWallet`
    2. `asset`
    3. `conditionId`
    4. `size`
    5. `avgPrice`
    6. `initialValue`
    7. `currentValue`
    8. `cashPnl`
    9. `percentPnl`
    10. `totalBought`
    11. `realizedPnl`
    12. `percentRealizedPnl`
    13. `curPrice`
    14. `redeemable`
    15. `mergeable`
    16. `title`
    17. `slug`
    18. `icon`
    19. `eventId`
    20. `eventSlug`
    21. `outcome`
    22. `outcomeIndex`
    23. `oppositeOutcome`
    24. `oppositeAsset`
    25. `endDate`
    26. `negativeRisk`

**Key difference:** Activity shows historical transactions (what happened), while Positions shows current holdings with P&L calculations (what you have now).