'''
Get user current positions from given wallet address using raw requests to data-api.polymarket.com/positions
'''

import sys
import time
import json
import os
import requests

default_wallet_address = "0x0000000000000000000000000000000000000000"  # Replace with your wallet address
wallet_address = sys.argv[1] if len(sys.argv) > 1 else default_wallet_address
print(f"Fetching positions for {wallet_address}...")
print("-" * 80)
print("\n")

resp = requests.get(
    "https://data-api.polymarket.com/positions",
    params={"user": wallet_address},
    timeout=10
)
resp.raise_for_status()
data = resp.json()

# Save json
print(f"Completed: fetched {len(data)} total position entries", flush=True)
timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
os.makedirs("data/user-positions", exist_ok=True)
json_path = "data/user-positions/" + f"{wallet_address}-{timestamp}.json"
print(f"Saving {len(data)} entries to {json_path}...", flush=True)
with open(json_path, "w") as f:
    json.dump(data, f, indent=2)
print(f"Saved raw json to {json_path} ({len(data)} entries)", flush=True)

# Print output
for p in data:
    for key, value in p.items():
        print(f"  {key}: {value}")
    print("-" * 80)