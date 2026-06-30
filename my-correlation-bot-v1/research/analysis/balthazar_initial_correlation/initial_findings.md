# Initial Balthazar X/Polymarket Correlation Findings

## What Was Read

- X export: 17 posts, including 4 media posts.
- Polymarket master trades: 524,283 rows, 499,512 unique transaction hashes, 28,519 condition IDs.
- Trade coverage: `2025-02-07T19:57:10+00:00` through `2026-06-25T09:54:46+00:00`.
- Main derived files: `tweets_read_first.csv`, `tweet_trade_windows.csv`, `tweet_window_recent_baseline_comparison.csv`, `market_category_summary.csv`, `top_event_clusters.csv`, `side_outcome_summary.csv`.

## X Signal

The X account is not posting public picks. The collected posts are mostly about market mechanics: PnL trackers, platform tiers, API/rate limits, correlations/combinatorial markets, taker rebates, and EV fills.

Media added three useful clues:

- A rate-limit comparison screenshot calls out Polymarket order and cancel throughput, including high order/cancel rates.
- A correlation screenshot compares bid/ask price paths between two political markets with a score and lag control.
- A day-of-week gain table suggests he is already slicing realized performance by temporal features.

## Trading Shape

- BUY rows: 367,150; SELL rows: 157,133.
- Fill sizing is mostly small but frequent: median $13.02, p90 $99.80, p99 $340.00, max $18,735.55.
- Adjacent trade timing is highly automated-looking: median gap 0.0 seconds; 79.6% of adjacent rows are within 5 seconds.
- Exact-second bursts exist: 109 seconds have at least 50 trade rows; max is 112 rows in one second.
- Side/outcome concentration by USDC starts with BUY/No, which is consistent with baskets of mutually related outcomes, date ladders, or broad no-basket exposure.

Top side/outcome groups by USDC:

- BUY / No: 267,994 rows, $16,874,315, 20,838 markets.
- BUY / Yes: 86,389 rows, $2,403,577, 8,433 markets.
- SELL / Yes: 138,271 rows, $1,400,666, 11,134 markets.
- SELL / No: 17,941 rows, $872,284, 1,331 markets.
- BUY / Under: 4,561 rows, $151,566, 1,042 markets.
- BUY / Over: 3,566 rows, $139,415, 1,011 markets.

Top category buckets by USDC from the heuristic classifier:

- geopolitics: $7,172,182
- other: $4,623,879
- politics/elections: $3,358,024
- sports: $2,458,626
- tech/ai: $1,389,685
- culture/news: $1,029,940
- crypto: $858,109
- finance/macro: $656,336

## Tweet-Window Read

During the X-post period, a normal rolling 6h window has median $39,570, p90 $84,405, p95 $98,419, p99 $163,224. This is the right baseline, not all-history quiet periods.

Highest 6h-after-tweet windows by recent-period USDC percentile:

- 2026-06-14T17:49:24+00:00 | pctl 0.979 | $129,302 | 2,445 trades | @PolymarketDevs Taker rebates please🙏
- 2026-06-11T15:04:08+00:00 | pctl 0.957 | $101,202 | 2,945 trades | @datadashxyz @Polymarket @PolymarketIntel @PolymarketTrade Higher 📈 DMed
- 2026-06-09T14:25:31+00:00 | pctl 0.920 | $89,455 | 2,030 trades | @nicoco89poly @Polymarket @MatthewModabber 🐐
- 2026-06-15T16:57:56+00:00 | pctl 0.912 | $86,613 | 2,079 trades | @MonteCarloSpam Correlations are the best https://t.co/BlEuMqkuon
- 2026-06-15T19:35:13+00:00 | pctl 0.876 | $81,666 | 1,812 trades | @MonteCarloSpam Is Oprah long or short war?
- 2026-06-21T15:01:04+00:00 | pctl 0.837 | $74,637 | 2,051 trades | @MonteCarloSpam tfw 4k ev fill https://t.co/T8UunlcW8A
- 2026-06-08T13:14:12+00:00 | pctl 0.758 | $60,498 | 1,270 trades | road to plat
- 2026-06-03T21:15:29+00:00 | pctl 0.573 | $43,397 | 1,628 trades | @datadashxyz @Polymarket @PolymarketIntel @PolymarketTrade I wish I had 940k PNL I wonder where these ridiculo

Interpretation: several post windows land in high-activity periods, especially the taker-rebate, rate-limit, correlation, and EV-fill posts. That is suggestive, but not causal by itself because his baseline activity in this period is already very high.

## Event/Market Cluster Read

The largest event clusters are multi-market baskets, not isolated markets. Examples from `top_event_clusters.csv` include US/Iran strike date ladders, crypto insider-trading outcome sets, and Iran Supreme Leader candidate baskets.

- `us-next-strikes-iran-on-843`: 24,938 rows, $1,601,497, 30 markets; top title: Will the US next strike Iran on February 28, 2026 (ET)?
- `which-crypto-company-will-zachxbt-expose-for-insider-trading`: 15,016 rows, $1,506,388, 28 markets; top title: Will Meteora be accused of insider trading?
- `who-will-be-next-supreme-leader-of-iran-515`: 14,116 rows, $1,399,803, 40 markets; top title: Will Mojtaba Khamenei be the next Supreme Leader of Iran?
- `us-strikes-iran-by`: 10,607 rows, $645,621, 44 markets; top title: US strikes Iran by February 28, 2026?
- `military-action-against-iran-ends-on-127`: 2,851 rows, $516,694, 26 markets; top title: Military action against Iran ends on April 10, 2026?
- `peru-presidential-election-winner`: 6,267 rows, $468,139, 23 markets; top title: Will Roberto Sánchez Palomino win the 2026 Peruvian presidential election?

## Initial Bot-Style Hypothesis

Most likely: an API-driven correlation/combinatorial execution bot, not a simple directional picks bot. The behavior looks like it scans related outcome sets, prices or ranks pairwise correlations, and executes many small fills across markets where the combined basket has positive expected value.

Supporting evidence:

- X posts explicitly discuss rate limits, API order/cancel behavior, correlations, combinatorial quotes, taker rebates, and EV fills.
- Media shows a correlation scoring chart with bid/ask paths and lag, plus a rate-limit/order-cancel comparison.
- Trading is dense and fast: hundreds of thousands of rows, same-second clustering, and many bursts across dozens of markets.
- Largest clusters are related baskets: date ladders, candidate sets, exact-score/sports outcome groups, crypto-company accusation sets, and Iran/geopolitics groups.
- BUY/No dominates the USDC footprint, matching broad basket-style trades where many alternatives should resolve No or where no-side prices are misaligned across related markets.

Secondary possibility: a market-making or stale-quote sniping layer may sit underneath the correlation model. The taker-rebate and hot-order/cancel posts point to execution economics, but public fills alone cannot prove maker/taker status or cancel strategy.

## Caveats

- This is public fills plus public posts only. It does not include live order book snapshots, order-placement logs, cancel logs, private inventory, or exact model signals.
- `closed_positions.csv` can duplicate row-level PnL by market/outcome; rough sums should be treated as directional, not authoritative portfolio PnL.
- Timing correlation needs a stricter matched baseline before claiming a post caused or revealed a trade.
