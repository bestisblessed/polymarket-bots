'''
Get holdings value for a user given wallet address
'''

import requests

wallet_address = "0x7fBCC3c7D3854016754ec186d8865DccD11a3533"

resp = requests.get(
    "https://data-api.polymarket.com/value",
    params={"user": wallet_address},
    timeout=10
)
resp.raise_for_status()
data = resp.json()
value = data[0]["value"]
print(f"Total holdings value for {wallet_address}: ${value:,.2f}")