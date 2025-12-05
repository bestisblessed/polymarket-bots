'''
Test and display all available user endpoints from Polymarket Data API
'''

import sys
import json
import requests

default_wallet_address = "0x7fBCC3c7D3854016754ec186d8865DccD11a3533"
wallet_address = sys.argv[1] if len(sys.argv) > 1 else default_wallet_address

base_url = "https://data-api.polymarket.com"

endpoints = [
    {
        "name": "Activity",
        "path": "/activity",
        "params": {"user": wallet_address, "limit": 5},
        "description": "On-chain user activity (trades, buys, sells, etc)"
    },
    {
        "name": "Value",
        "path": "/value",
        "params": {"user": wallet_address},
        "description": "Total holdings value across all markets"
    },
    {
        "name": "Positions",
        "path": "/positions",
        "params": {"user": wallet_address, "limit": 5},
        "description": "Current positions across all markets"
    },
    {
        "name": "Trades",
        "path": "/trades",
        "params": {"user": wallet_address, "limit": 5},
        "description": "Trade history for the user"
    }
]

print("=" * 80)
print(f"Testing Polymarket Data API User Endpoints")
print(f"Wallet Address: {wallet_address}")
print("=" * 80)
print()

for endpoint in endpoints:
    print(f"\n{'=' * 80}")
    print(f"Endpoint: {endpoint['name']} ({endpoint['path']})")
    print(f"Description: {endpoint['description']}")
    print(f"{'=' * 80}")
    
    url = base_url + endpoint['path']
    
    try:
        resp = requests.get(url, params=endpoint['params'], timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        print(f"Status: SUCCESS (HTTP {resp.status_code})")
        print(f"Response Type: {type(data).__name__}")
        
        if isinstance(data, list):
            print(f"Number of Items: {len(data)}")
            if len(data) > 0:
                print(f"\nFirst Item Structure:")
                print(json.dumps(data[0], indent=2))
                if len(data) > 1:
                    print(f"\n... and {len(data) - 1} more item(s)")
        elif isinstance(data, dict):
            print(f"\nResponse Structure:")
            print(json.dumps(data, indent=2))
        else:
            print(f"\nResponse:")
            print(data)
            
    except requests.exceptions.HTTPError as e:
        print(f"Status: HTTP ERROR ({e.response.status_code})")
        try:
            error_data = e.response.json()
            print(f"Error Details: {json.dumps(error_data, indent=2)}")
        except:
            print(f"Error Details: {e.response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Status: REQUEST ERROR")
        print(f"Error: {str(e)}")
    except Exception as e:
        print(f"Status: ERROR")
        print(f"Error: {str(e)}")
    
    print()

print("=" * 80)
print("Summary of Available Endpoints:")
print("=" * 80)
for endpoint in endpoints:
    print(f"  • {endpoint['path']} - {endpoint['description']}")
print()

