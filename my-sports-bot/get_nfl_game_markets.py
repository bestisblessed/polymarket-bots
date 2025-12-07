import requests
import json
import os

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"

print("Fetching NFL game markets (spreads, totals, moneylines)...")

NFL_GAME_TAG_ID = "100639"

all_game_markets = []
limit = 100
offset = 0

while True:
    params = {
        "tag_id": NFL_GAME_TAG_ID,
        "limit": limit,
        "offset": offset,
        "closed": "false",
    }
    r = requests.get(f"{GAMMA_BASE_URL}/markets", params=params)
    batch = r.json()
    if not batch:
        break
    
    for m in batch:
        if m.get("sportsMarketType") not in ["spreads", "totals", "moneyline"]:
            continue
        
        slug = m.get("slug", "").lower()
        events = m.get("events", [])
        
        is_nfl = False
        if slug.startswith("nfl-"):
            is_nfl = True
        elif events:
            for event in events:
                series_slug = event.get("seriesSlug", "").lower()
                if "nfl" in series_slug:
                    is_nfl = True
                    break
        
        if is_nfl:
            all_game_markets.append(m)
    
    offset += limit
    if len(batch) < limit:
        break

unique_markets = {}
for m in all_game_markets:
    mid = m.get("id")
    if mid is not None:
        unique_markets[mid] = m

game_markets_list = list(unique_markets.values())

os.makedirs("data", exist_ok=True)
with open("data/nfl_game_markets.json", "w") as f:
    json.dump(game_markets_list, f, indent=2)

print(f"\nSuccess! Saved {len(game_markets_list)} NFL game markets to 'data/nfl_game_markets.json'")
