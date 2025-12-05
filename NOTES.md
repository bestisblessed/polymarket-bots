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