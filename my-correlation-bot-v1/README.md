# my-correlation-bot-v1

Initial research workspace for learning from `@balthazarpoly` X posts/replies and Polymarket activity.

## X Export

Raw `bird-keychain` captures are saved under `data/x_balthazarpoly/raw/`.

Normalized analysis files are saved beside them:

- `tweets_combined.json` and `tweets_combined.jsonl` preserve deduped tweets with raw tweet payloads.
- `tweets_combined.csv` is a compact table for spreadsheets and notebooks.
- `media/` contains downloaded tweet media.
- `media_manifest.csv` and `media_manifest.json` map tweet ids to local media files.

Refresh the normalized files after recapturing raw data:

```bash
python my-correlation-bot-v1/scripts/normalize_x_export.py \
  --raw-dir my-correlation-bot-v1/data/x_balthazarpoly/raw \
  --out-dir my-correlation-bot-v1/data/x_balthazarpoly
```

## Official X API Export

Read-only official X API wrappers live in `scripts/` and use `my-correlation-bot-v1/.env`.

The local `.env` should contain only:

```bash
X_BEARER_TOKEN="..."
```

Useful commands:

```bash
# Verify auth with one tiny user lookup.
bash my-correlation-bot-v1/scripts/x_auth_check.sh

# Refresh and save the app-only bearer token from X_API_KEY/X_API_SECRET.
bash my-correlation-bot-v1/scripts/x_refresh_bearer.sh

# Resolve a username to an official X user id and public metrics.
bash my-correlation-bot-v1/scripts/x_lookup_user.sh balthazarpoly

# Check project post-read usage and monthly cap.
bash my-correlation-bot-v1/scripts/x_usage.sh

# Cheap smoke test: one timeline page plus one full-archive search page, no media downloads.
bash my-correlation-bot-v1/scripts/x_smoke_test.sh balthazarpoly

# Export timeline + full-archive search, normalize JSON/JSONL/CSV, and download media.
bash my-correlation-bot-v1/scripts/export_x_user_official.sh balthazarpoly
```

If you see `401 Unauthorized`, run `x_refresh_bearer.sh` once. The exporter also retries one time with a freshly minted app-only bearer token when `X_API_KEY` and `X_API_SECRET` are present in `.env`.

The official export writes to `data/x_official_<username>/`:

- `raw/user.json`
- `raw/timeline_pages.json`
- `raw/search_all_pages.json` or `raw/search_all_error.json`
- `tweets_combined.json`, `tweets_combined.jsonl`, and `tweets_combined.csv`
- `media/` and `media_manifest.json`
- `summary.json`

Full-archive search requires the app's X API access level to allow `/2/tweets/search/all`. If that endpoint is denied, the exporter records the error and falls back to recent search unless `--no-recent-fallback` is passed.

## Polymarket Export

Public wallet activity for `0x5a218c7ad04135830a45c41aaed7294df7809318` is saved under `research/poly/data/polymarket_balthazar/`.

Refresh the Polymarket export:

```bash
python my-correlation-bot-v1/research/poly/export_polymarket_activity.py
```

The exporter captures raw Data API responses plus normalized CSV/JSONL files for activity, trades, current positions, closed positions, market summaries, combo data, and a combined `correlation_timeline.csv` with the X export from `research/x/data/x_official_balthazarpoly/` by default.

The public `/activity` endpoint can be walked farther back for trade rows by using timestamp windows:

```bash
python my-correlation-bot-v1/research/poly/export_polymarket_trade_history_windows.py
```

That produces `trade_transactions_master.*` and `trade_transactions_market_summary.*` files.

When `/activity` timestamp windows are unavailable, the largest currently reachable `/trades` export can be refreshed with:

```bash
python my-correlation-bot-v1/research/poly/export_polymarket_trades_public_cap.py
```

That produces `trade_transactions_public_cap_master.*` and records whether the public cap was still hit.
