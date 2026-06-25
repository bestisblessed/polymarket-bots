# my-correlation-bot-v1 Agent Notes

## Purpose

This workspace is for researching public signals around `@balthazarpoly` and the Polymarket wallet `0x5a218c7ad04135830a45c41aaed7294df7809318`.

The immediate goal is to correlate public X posts/replies/media with public Polymarket trading behavior, then use the resulting datasets for later strategy analysis, timing analysis, and bot-behavior research.

## Data Sources Collected

### X / Twitter: `@balthazarpoly`

- Location: `research/x/data/x_official_balthazarpoly/`
- Export method: official X API scripts in `research/x/`
- Main files:
  - `tweets_combined.csv`
  - `tweets_combined.jsonl`
  - `tweets_combined.json`
  - `media_manifest.json`
  - `media/`
  - `summary.json`
- Current snapshot summary: 17 tweets, 4 media items downloaded.
- Use this source for timestamps, tweet text, reply/thread context, media references, and URL-level provenance.

### Polymarket: `balthazar`

- Location: `research/poly/data/polymarket_balthazar/`
- Export method: public Polymarket Data API scripts in `research/poly/`
- Main files:
  - `trade_transactions_master.csv` / `.jsonl` / `.json`
  - `trade_transactions_market_summary.csv`
  - `positions_current.csv`
  - `closed_positions.csv`
  - `activity.csv`
  - `correlation_timeline.csv`
  - `summary.json`
  - `metadata.json`
- Current full trade snapshot summary: 524,283 deduped trade rows across 151 timestamp windows, covering `2025-02-07T19:57:10+00:00` through `2026-06-25T09:54:46+00:00`.
- Current broad snapshot summary: 3,500 recent activity rows, 1,000 recent `/trades` rows, 9,061 current positions, and 50,874 closed positions.
- Use `trade_transactions_master.*` as the source of truth for full public trade history. The smaller `activity.*` and `trades.*` files are recent/capped snapshots.

## How To Use The Data

- Prefer `.csv` for notebooks, spreadsheets, DuckDB, and quick inspection.
- Prefer `.jsonl` for streaming or large programmatic processing.
- Use `raw/` only for audit, debugging, or re-normalizing exports.
- Treat all timestamps as UTC unless a file explicitly says otherwise.
- For X-to-trade analysis, start with `correlation_timeline.csv`, then join back to `tweets_combined.*` and `trade_transactions_master.*` for richer fields.
- Useful research cuts include trade timing around posts, market/outcome clustering, position sizing, repeated market categories, realized closed-position performance, and current exposure.
- Do not infer causality from timing alone; preserve source timestamps and raw IDs so analysis can be audited.

## Script Notes

- Broad Polymarket refresh:
  - `python research/poly/export_polymarket_activity.py`
- Full trade-history refresh:
  - `python research/poly/export_polymarket_trade_history_windows.py --max-windows 500`
- Both Polymarket exporters resume from ignored checkpoints by default. Use `--force-refresh` only when intentionally rebuilding from the API.
- X API helper scripts live in `research/x/` and require local credentials in `research/x/.env`; never commit secrets.

## Guardrails

- `research/*/data/` is runtime data and should stay ignored unless the user explicitly asks to force-add selected snapshot files.
- Keep public-data provenance intact: wallet address, tweet IDs, transaction hashes, timestamps, market slugs, and summary metadata matter.
- Do not add private credentials, paid API dumps, or non-public user data to this project.
- If rerunning exports, update summaries or documentation when row counts, coverage windows, or source paths materially change.
