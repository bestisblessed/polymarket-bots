'''
List top 50 markets by volume
'''

from polymarket_apis import PolymarketGammaClient

gamma = PolymarketGammaClient()
markets = gamma.get_markets(closed=False, limit=1000)
markets = sorted(markets, key=lambda m: (m.volume_num or 0), reverse=True)[:50]

for m in markets:
    print(f"{m.slug}  -  Volume: ${m.volume_num}")
    # print(f"{m.slug}:   VOLUME ${m.volume_num}")
    # (id={m.id})