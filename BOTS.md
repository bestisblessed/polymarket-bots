- **Market screener bot**
  - Uses: `Gamma` (direct REST or `PolymarketGammaClient`), maybe GraphQL.
  - Finds new markets by category/liquidity; scores them by volume / OI; outputs a watchlist.

- **Directional trading bot**
  - Uses: `PolymarketGammaClient` + `PolymarketClobClient` (+ WebSockets for fills).
  - Pull markets → compute fair value with your model → call `place_order` to trade mispricings.

- **Market‑making / liquidity provision bot**
  - Uses: `PolymarketGammaClient` + `PolymarketClobClient` + `PolymarketWebsocketsClient`.
  - Streams orderbook updates, keeps quotes around mid, manages inventory.

- **PnL / risk monitor**
  - Uses: `PolymarketDataClient` + GraphQL subgraphs.
  - Periodically pulls positions & PnL, applies risk limits, possibly triggers hedges via CLOB.

- **Copy‑trading or leaderboard‑following bot**
  - Uses: `PolymarketDataClient` for leaderboards/holders, `PolymarketClobClient` for mirroring trades.