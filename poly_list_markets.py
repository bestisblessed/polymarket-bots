from polymarket_apis import PolymarketGammaClient

gamma = PolymarketGammaClient()
markets = gamma.get_markets()

# sort by numeric volume descending (falls back to 0 if missing)
markets = sorted(markets, key=lambda m: (m.volume_num or 0), reverse=True)

for m in markets:
    print(f"{m.category}: {m.slug} - VOLUME ${m.volume_num}")
    # {m.id}
    # {m.question[:80]}