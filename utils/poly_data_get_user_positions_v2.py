'''
Get user current positions from given wallet address using PolymarketDataClient
'''
# Fetches current positions for a given wallet address and provides:
# - Position sizes, prices, and P&L calculations
# - Realized and unrealized gains/losses
# - Market details and outcomes
# - Risk management data for trading bots

# Useful for:
# - Risk controls in bots (limit exposure across markets)
# - P&L tracking / analytics dashboards
# - Copy-trading or leader-following strategies
# - Portfolio optimization and rebalancing

import json
from polymarket_apis import PolymarketDataClient

data = PolymarketDataClient()
wallet_address = "0x0000000000000000000000000000000000000000"  # Replace with your wallet address
positions = data.get_positions(user=wallet_address)

for p in positions:
    print(p)
    # print(p.market_title, p.outcome, p.size, p.pnl)

positions_dicts = [p.model_dump() for p in positions]
with open("data/user-positions.json", "w") as f:
    json.dump(positions_dicts, f, indent=2, default=str)
print(f"Saved {len(positions)} positions to data/user-positions.json")
