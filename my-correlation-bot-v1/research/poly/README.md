# Polymarket Research Scripts

These scripts export public Polymarket wallet data for `balthazar` research and X/trade correlation analysis.

| Script | What it does | Use it for |
|---|---|---|
| `export_polymarket_activity.py` | Broad wallet snapshot exporter. Pulls Polymarket activity, trades, current positions, closed positions, value, combo positions/activity, and builds `correlation_timeline.csv` against the X tweet export. | General research snapshots and X-vs-Polymarket correlation analysis. |
| `export_polymarket_trade_history_windows.py` | Full trade-history exporter. Uses `/activity` with `type=TRADE` and timestamp windows to work around the public offset cap. Writes `trade_transactions_master.*`, market summaries, and raw window pages. | Main/final script for full trade transaction history. |
| `total-txs.sh` | Small curl/jq helper that probes `/trades` at offsets `0` and `10000`, then prints row count and unique transaction hashes. | Quick sanity check for whether the old `/trades` endpoint is capped or incomplete. |

## Output Formats

| Format | What it is | Use it for |
|---|---|---|
| `.csv` | Flat spreadsheet/dataframe version of the export. | First choice for notebooks, DuckDB, pandas, spreadsheets, and quick inspection. |
| `.jsonl` | One JSON object per line. | Best for streaming or programmatic processing of large row sets. |
| `.json` | Full JSON array or metadata object. | Best when preserving nested data or reading the whole file at once. |
| `raw/` | Raw Polymarket API responses and window pages used to build the normalized files. | Debugging, reproducibility, and re-normalizing later. Not usually needed for final analysis. |

## Important Output Files

Files are written under `research/poly/data/polymarket_balthazar/`.

| File or file group | Rows | What it contains | Use it for |
|---|---:|---|---|
| `trade_transactions_master.csv` / `.jsonl` / `.json` | 524,283 | Complete deduped TRADE activity from the timestamp-window exporter, with side, market, outcome, size, price, USDC size, transaction hash, and source windows. Covers `2025-02-07T19:57:10+00:00` through `2026-06-25T09:54:46+00:00`. | Main trade-history dataset for modeling, bot-behavior analysis, market timing, sizing, and strategy reconstruction. |
| `trade_transactions_market_summary.csv` / `.jsonl` / `.json` | 45,563 | Aggregates `trade_transactions_master.*` by market/outcome/side with trade count, total USDC size, total tokens, first/last timestamps, unique transaction count, and sample hashes. | Fast market-level analysis without scanning the full 524k-row master file. |
| `trade_transactions_master_summary.json` | 1 metadata object | Completion metadata for the full trade-history export: window count, row counts, duplicate overlap, oldest/newest timestamps, and stop reason. | Confirming whether the full windowed export completed cleanly. |
| `positions_current.csv` / `.jsonl` / `.json` | 9,061 | Current open positions with size, average price, current price, initial/current value, cash PnL, percent PnL, and market metadata. | Current exposure, portfolio concentration, and active-position analysis. |
| `closed_positions.csv` / `.jsonl` / `.json` | 50,874 | Closed/resolved historical positions with realized PnL and market metadata. | Outcome-level performance analysis and realized PnL review. |
| `activity.csv` / `.jsonl` / `.json` | 3,500 | Broad recent wallet activity from `/activity`, including trades and other activity types when present. | Recent activity inspection. Use `trade_transactions_master.*` instead for full trade history. |
| `activity_market_summary.csv` / `.jsonl` / `.json` | 1,072 | Market/outcome/side summary built from the smaller `activity.*` snapshot. | Quick recent-market summary. Use `trade_transactions_market_summary.*` for the full-history version. |
| `trades.csv` / `.jsonl` / `.json` | 1,000 | Recent `/trades` endpoint snapshot. This is useful but endpoint-capped compared with the windowed activity export. | Lightweight comparison/debug dataset, not the full trade source of truth. |
| `correlation_timeline.csv` | 3,517 | Combined timeline rows from Polymarket activity and the official X tweet export. Includes source, timestamp, market/title, trade side/outcome/amount, tweet text, and tweet URL fields. | Time-aligning X posts with Polymarket behavior. |
| `summary.json` | 1 metadata object | High-level counts from the broad activity exporter plus current account value from `/value`. | Quick sanity check and dashboard summary. |
| `metadata.json` | 1 metadata object | Export settings, Polymarket docs links, endpoint pagination metadata, and completion/stop reasons for the broad exporter. | Audit trail for how the broad export was generated. |
| `combo_positions.json` / `combo_activity.json` | 0 in this export | Combo position/activity endpoint results. These were empty for the captured wallet run. | Keep only to prove combo endpoints were checked. |
| `raw/activity_trade_windows/window_*.json` | 151 files | Raw timestamp-window API pages that produced `trade_transactions_master.*`. | Repro/debug only. The normalized master files are the final analysis outputs. |
