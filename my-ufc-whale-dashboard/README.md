# UFC Whale Dashboard

Fetch and analyze top holders for all UFC markets on Polymarket.

## Scripts

### `get_ufc_event_slugs.py`
Lists all active UFC event slugs with moneyline markets.

```bash
python3 get_ufc_event_slugs.py
```

### `fetch_ufc_market_holders.py`
Fetches top 20 holders for all markets across all active UFC fights and saves data to JSON files.

```bash
# Fetch all active UFC events
python3 fetch_ufc_market_holders.py

# Fetch a specific event
python3 fetch_ufc_market_holders.py ufc-ale14-die4-2026-01-31
```

## Output

Data is saved to the `data/` directory:
- Individual event files: `{event_slug}_{timestamp}.json`
- Summary file: `ufc_holders_summary_{timestamp}.json`

## APIs Used

| API | Endpoint | Purpose |
|-----|----------|---------|
| Gamma API | `GET /events?tag_slug=ufc` | Fetch UFC events and markets |
| Data API | `GET /holders?market={conditionId}` | Fetch top holders for each market |

## References

- [List Events](https://docs.polymarket.com/api-reference/events/list-events)
- [Get Top Holders for Markets](https://docs.polymarket.com/api-reference/core/get-top-holders-for-markets)
