'''
Get holdings value for a user given wallet address
'''

import sys
import requests

default_wallet_address = "0x0000000000000000000000000000000000000000"  # Replace with your wallet address
wallet_address = sys.argv[1] if len(sys.argv) > 1 else default_wallet_address

resp = requests.get(
    "https://data-api.polymarket.com/value",
    params={"user": wallet_address},
    timeout=10
)
resp.raise_for_status()
data = resp.json()
value = data[0]["value"]
print(f"Total holdings value for {wallet_address}: ${value:,.2f}")