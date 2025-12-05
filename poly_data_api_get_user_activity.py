# Get user activity from given wallet address (buys, sells, etc)
import requests

resp = requests.get(
    "https://data-api.polymarket.com/activity",
    params={"user": "0x7fBCC3c7D3854016754ec186d8865DccD11a3533"},
    timeout=10
)
resp.raise_for_status()
print(resp.json())