import requests
import json
import os
import csv

NFL_TAG_ID = "10"
all_markets = []
offset = 0
limit = 100

print("Fetching ALL active NFL markets...")
while True:
    params = {
        "tag_id": NFL_TAG_ID,
        "closed": False,
        "limit": limit,
        "offset": offset,
        "order": "id",
        "ascending": False
    }
    resp = requests.get("https://gamma-api.polymarket.com/events", params=params)
    batch = resp.json()
    if not batch:
        break
    print(f"Fetched {len(batch)} events (Total markets: {len(all_markets)})...")
    for event in batch:
        markets = event.get("markets", [])
        for m in markets:
            if isinstance(m, dict):
                m["event_title"] = event.get("title")
                m["event_slug"] = event.get("slug")
                all_markets.append(m)
    if len(batch) < limit:
        break
    offset += limit

# Save json
os.makedirs("data", exist_ok=True)
with open("data/nfl_markets.json", "w") as f:
    json.dump(all_markets, f, indent=2)

# Save CSV
csv_path = "data/nfl_markets.csv"
all_keys = set()
for m in all_markets:
    all_keys.update(m.keys())
keys = sorted(list(all_keys))
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=keys)
    writer.writeheader()
    writer.writerows(all_markets)
print(f"- {csv_path}")
print(f"\nSuccess! Saved {len(all_markets)} NFL markets to 'data/nfl_markets.json'")
