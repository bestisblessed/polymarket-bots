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
print(f"Fetching markets in '{TARGET_CATEGORY}' category (id: {CATEGORY_ID})..")
try:
    markets_response = requests.get(f"https://gamma-api.polymarket.com/markets?category_id={CATEGORY_ID}&closed=false&limit=1000")
    markets_data = markets_response.json()
    print(f'Found {len(markets_data)} markets in {TARGET_CATEGORY}')

    # Print first 10
    print('First 10 markets:')
    for i, m in enumerate(markets_data[:10], 1):
        print(f"{i}. {m.get('slug', 'unknown')}")

    # Save all to JSON
    os.makedirs("data", exist_ok=True)
    with open(f"data/markets_{TARGET_CATEGORY.lower()}.json", "w") as f:
        json.dump(markets_data, f, indent=2, default=str)
    print(f"Saved {len(markets_data)} markets to data/markets_{TARGET_CATEGORY.lower()}.json")
    
except Exception as e:
    print(f"Error: {e}")

