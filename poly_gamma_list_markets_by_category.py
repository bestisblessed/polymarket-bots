'''
List markets by given category
'''
import json
import os
import requests

CATEGORY_IDS = {
    "Politics": "5481",
    "Finance": "5510",
    "Crypto": "5466",
    "Sports": "5487",
    "Tech": "5462"
}
TARGET_CATEGORY = "Finance"
CATEGORY_ID = CATEGORY_IDS.get(TARGET_CATEGORY)
print(f"Fetching ALL markets in '{TARGET_CATEGORY}'...")

try:
    all_markets = []
    offset = 0
    batch_size = 500
    while True:
        params = {
            "category_id": CATEGORY_ID,
            "closed": False,
            "limit": batch_size,
            "offset": offset
        }
        response = requests.get("https://gamma-api.polymarket.com/markets", params=params)
        markets_batch = response.json()
        if not markets_batch:
            break
        all_markets.extend(markets_batch)
        print(f"  Batch {len(all_markets)//batch_size + 1}: {len(markets_batch)} markets (total: {len(all_markets)})")
        if len(markets_batch) < batch_size:
            break
        offset += batch_size
    markets_data = all_markets
    print(f'\nFound {len(markets_data)} TOTAL markets in {TARGET_CATEGORY}')

    # Print first 10
    print('First 10 markets:')
    for i, m in enumerate(markets_data[:10], 1):
        print(f"{i}. {m.get('slug', 'unknown')}")

    # Save all to JSON
    os.makedirs("data", exist_ok=True)
    with open(f"data/category_{TARGET_CATEGORY.lower()}.json", "w") as f:
        json.dump(markets_data, f, indent=2, default=str)
    print(f"Saved {len(markets_data)} markets to data/category_{TARGET_CATEGORY.lower()}.json")

except Exception as e:
    print(f"Error: {e}")