# Polymarket Research Scripts

These scripts export public Polymarket wallet data for `balthazar` research and X/trade correlation analysis.

| Script | What it does | Use it for |
|---|---|---|
| `export_polymarket_activity.py` | Broad wallet snapshot exporter. Pulls Polymarket activity, trades, current positions, closed positions, value, combo positions/activity, and builds `correlation_timeline.csv` against the X tweet export. | General research snapshots and X-vs-Polymarket correlation analysis. |
| `export_polymarket_trade_history_windows.py` | Full trade-history exporter. Uses `/activity` with `type=TRADE` and timestamp windows to work around the public offset cap. Writes `trade_transactions_master.*`, market summaries, and raw window pages. | Main/final script for full trade transaction history. |
| `total-txs.sh` | Small curl/jq helper that probes `/trades` at offsets `0` and `10000`, then prints row count and unique transaction hashes. | Quick sanity check for whether the old `/trades` endpoint is capped or incomplete. |

