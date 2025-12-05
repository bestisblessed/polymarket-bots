'''
Get user activity from given wallet address (buys, sells, etc)
'''

import sys
import time
import requests

default_wallet_address = "0x7fBCC3c7D3854016754ec186d8865DccD11a3533"
wallet_address = sys.argv[1] if len(sys.argv) > 1 else default_wallet_address

resp = requests.get(
    "https://data-api.polymarket.com/activity",
    params={"user": wallet_address},
    timeout=10
)
resp.raise_for_status()

data = resp.json()
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
