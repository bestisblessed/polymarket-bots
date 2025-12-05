'''
Get user activity from given wallet address (buys, sells, etc)
'''

import sys
import time
import json
import os
import requests

default_wallet_address = "0x7fBCC3c7D3854016754ec186d8865DccD11a3533"
wallet_address = sys.argv[1] if len(sys.argv) > 1 else default_wallet_address
print(f"Fetching activity for {wallet_address}...")
print("-" * 80)
print("\n")

all_data = []
offset = 0
limit = 500
page_num = 1

# Loop through activity pages
while True:
    print(f"Fetching page {page_num} (offset: {offset})...", end=" ", flush=True)
    resp = requests.get(
        "https://data-api.polymarket.com/activity",
        params={"user": wallet_address, "limit": limit, "offset": offset},
        timeout=10
    )
    resp.raise_for_status()
    page_data = resp.json()
    if not page_data:
        print("no more data", flush=True)
        break
    all_data.extend(page_data)
    print(f"got {len(page_data)} entries", flush=True)
    if len(page_data) < limit:
        break
    offset += limit
    page_num += 1

# Save json
data = all_data
print(f"\nCompleted: fetched {len(data)} total activity entries (max per request: {limit})", flush=True)
timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
os.makedirs("data/user-activity", exist_ok=True)
json_path = "data/user-activity/" + f"{wallet_address}-{timestamp}.json"
print(f"Saving {len(data)} entries to {json_path}...", flush=True)
with open(json_path, "w") as f:
    json.dump(data, f, indent=2)
print(f"Saved raw json to {json_path} ({len(data)} entries)", flush=True)

# Print output
for t in data:
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(t.get("timestamp", 0)))
    title = t.get("title", "")
    side = t.get("side", "")
    size = t.get("size", "")
    price = t.get("price", "")
    usdc = t.get("usdcSize", "")
    outcome = t.get("outcome", "")
    tx = t.get("transactionHash", "")
    print(f"{title}")
    print(f"  {ts}  {side} {size} @ {price}  (${usdc} USDC)  -> {outcome}")
    print(f"  tx: {tx}")
    print("-" * 80)
