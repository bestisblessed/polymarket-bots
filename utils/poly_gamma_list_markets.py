'''
Fetch and list all markets using PolymarketGammaClient
'''
# List and search markets (status, tags, series, sports, etc.).
# Pull event metadata, categories, resolution info.
# Build screeners / watchlists your trading logic uses.
# Example (from the library docs)

import json
from polymarket_apis import PolymarketGammaClient

gamma = PolymarketGammaClient()
markets = gamma.get_markets(closed=False)

# Print output
for m in markets:
    print(m)

# Save the markets data to a JSON file in 'data/'
with open("data/markets_v2.json", "w") as f:
    markets_dicts = [m.model_dump() for m in markets]
    json.dump(markets_dicts, f, indent=2, default=str)
print(f"\nSaved {len(markets)} markets to data/markets_v2.json")