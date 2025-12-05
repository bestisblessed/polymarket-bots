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

resp = requests.get(
    "https://data-api.polymarket.com/activity",
    params={"user": wallet_address},
    timeout=10
)
resp.raise_for_status()

# Save raw json
data = resp.json()
timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
os.makedirs("data/user-activity", exist_ok=True)
json_path = "data/user-activity/" + f"{wallet_address}-{timestamp}.json"
with open(json_path, "w") as f:
    json.dump(data, f, indent=2)
print(f"saved raw json to {json_path}")
time.sleep(1)

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
