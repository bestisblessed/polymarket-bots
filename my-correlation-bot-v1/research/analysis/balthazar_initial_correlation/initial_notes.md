# Balthazar Initial X/Polymarket Correlation Notes

## Source Coverage
- X posts read: 17 from `/Users/td/Code/polymarket-bots/my-correlation-bot-v1/research/x/data/x_official_balthazarpoly/tweets_combined.json`.
- Polymarket trade rows: 524,283, 2025-02-07T19:57:10+00:00 to 2026-06-25T09:54:46+00:00.
- Unique transactions: 499,512; unique markets/conditions: 28,519.

## X Post Themes
- 2026-05-21T22:43:35+00:00 | media=0 | tags=pnl/tracker;tier/volume | @Dr_PNL wV s*p*(1-p) is much lower than traditional vol s*p, not many reach beyond Gold
- 2026-05-31T15:26:07+00:00 | media=1 | tags=pnl/tracker | @Dr_PNL @Polymarket Is it? https://t.co/QT4QvwZE9z
- 2026-06-03T07:46:59+00:00 | media=0 | tags=api/rate-limit | API users used to be able to keep a flow of hot orders and cancel if they didn't want to buy, bypassing the delay. Now the spam is over. https://t.co/NmilRWYSDt
- 2026-06-03T21:15:29+00:00 | media=0 | tags=pnl/tracker | @datadashxyz @Polymarket @PolymarketIntel @PolymarketTrade I wish I had 940k PNL I wonder where these ridiculous figures come from
- 2026-06-03T21:16:35+00:00 | media=0 | tags=pnl/tracker | @datadashxyz @Polymarket @PolymarketIntel @PolymarketTrade I haven't seen a single tracker get my PNL right, predictfolio is closest but still wrong
- 2026-06-04T12:22:46+00:00 | media=1 | tags=api/rate-limit;tier/volume | Fun fact: Polymarket offers insanely high rate limits for everyone https://t.co/XaOQfau4re
- 2026-06-04T12:28:36+00:00 | media=0 | tags=tier/volume | Kalshi also has higher tiers gated behind inscrutable forms, the highest of which (Prime) is still half as what Polymarket offers
- 2026-06-05T14:24:52+00:00 | media=0 | tags=none | @Eltonma 🔥
- 2026-06-08T13:14:12+00:00 | media=0 | tags=tier/volume | road to plat
- 2026-06-09T05:07:24+00:00 | media=0 | tags=none | @3738283e convert
- 2026-06-09T14:25:31+00:00 | media=0 | tags=none | @nicoco89poly @Polymarket @MatthewModabber 🐐
- 2026-06-11T15:04:08+00:00 | media=0 | tags=none | @datadashxyz @Polymarket @PolymarketIntel @PolymarketTrade Higher 📈 DMed
- 2026-06-11T22:50:20+00:00 | media=0 | tags=correlation | Combinatorial module is impressive. Wish the quotes were a bit more transparent like the books. But chain-knows-all! https://t.co/5PQ6rXyU7o
- 2026-06-14T17:49:24+00:00 | media=0 | tags=rebates/fees | @PolymarketDevs Taker rebates please🙏
- 2026-06-15T16:57:56+00:00 | media=1 | tags=correlation | @MonteCarloSpam Correlations are the best https://t.co/BlEuMqkuon
- 2026-06-15T19:35:13+00:00 | media=0 | tags=none | @MonteCarloSpam Is Oprah long or short war?
- 2026-06-21T15:01:04+00:00 | media=1 | tags=execution/ev | @MonteCarloSpam tfw 4k ev fill https://t.co/T8UunlcW8A

## Trade Behavior Highlights
- BUY rows: 367,150; SELL rows: 157,133.
- Median USDC fill size: $13.02; p90 $99.80; p99 $340.00.
- Adjacent trade gaps: median 0.0 sec; 79.6% are <=5 sec.
- Top categories by USDC: geopolitics $7.17M, other $4.62M, politics/elections $3.36M, sports $2.46M, tech/ai $1.39M, culture/news $1.03M.

## Initial Interpretation
- The X account looks like a technical Polymarket operator, not a public picks account. Posts emphasize rate limits, API execution mechanics, correlations, combinatorial markets, EV fills, rebates, and PnL tracking.
- The trade history is far too dense for manual-only activity: same-second clustering, hundreds of thousands of rows, and repeated related-market baskets strongly suggest automation.
- The most plausible first hypothesis is a correlation/combinatorial arbitrage and execution bot: it scans related markets, sizes many small fills, and opportunistically captures EV across outcome sets, date ladders, and correlated sports/geopolitics/AI markets.
- Public fill history alone cannot prove maker-vs-taker logic or order-cancel behavior. Order book snapshots, open order/cancel logs, and WebSocket timing would be needed for that.
