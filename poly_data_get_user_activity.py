'''
Get user activity from given wallet address (buys, sells, etc)
'''

import requests

wallet_address = "0x7fBCC3c7D3854016754ec186d8865DccD11a3533"

resp = requests.get(
    "https://data-api.polymarket.com/activity",
    params={"user": wallet_address},
    timeout=10
)
resp.raise_for_status()
print(resp.json())