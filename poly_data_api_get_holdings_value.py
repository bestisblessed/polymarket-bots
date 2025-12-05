# Get holdings value for a user given wallet address
import requests

resp = requests.get(
    "https://data-api.polymarket.com/value",
    params={"user": "0x7fBCC3c7D3854016754ec186d8865DccD11a3533"},
    timeout=10
)
resp.raise_for_status()
print(resp.json())