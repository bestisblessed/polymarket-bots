# UFC Whale Dashboard (Data Exports)

This folder contains data export helpers for UFC markets on Polymarket.

## Scripts

### 1) `get_ufc_event_slugs.py`

Lists active UFC event slugs (events with moneyline markets) using the Gamma
`/events` endpoint filtered by `tag_slug=ufc`.

```
python3 "my UFC whale dashboard/get_ufc_event_slugs.py"
```

### 2) `fetch_ufc_market_holders.py`

Fetches the **top 20 holders** for **every market** in each UFC event slug and
saves the results to JSON + CSV for analysis.

```
python3 "my UFC whale dashboard/fetch_ufc_market_holders.py" \
  ufc-ale14-die4-2026-01-31 \
  ufc-raf-mau4-2026-01-31

# Or let it auto-discover slugs via get_ufc_event_slugs.py:
python3 "my UFC whale dashboard/fetch_ufc_market_holders.py"
```

#### Output files

Files are written under `data/ufc-holders/<event_slug>/`:

- `holders.json` - per-market top holders payloads
- `holders_flat.csv` - flattened rows for analytics
- `errors.json` - errors per market (if any)

A run summary is written to `data/ufc-holders/run_summary.json`.

## API References

- Gamma API events: https://docs.polymarket.com/api-reference/events/list-events.md
- Gamma API event by slug: https://docs.polymarket.com/api-reference/events/get-event-by-slug.md
- Data API holders: https://docs.polymarket.com/api-reference/core/get-top-holders-for-markets.md
