import requests
import json
import os
import sys

MARKET_ID = sys.argv[1] if len(sys.argv) > 1 else None

if not MARKET_ID:
    print("Usage: python3 get_game_bets_single.py <MARKET_ID>")
    print("\nExample: python3 get_game_bets_single.py 12345")
    print("\nTo find market IDs, run: python3 get_nfl_games.py")
    sys.exit(1)

print("Note: This script uses the Polymarket CLOB API /book endpoint")
print("Documentation: https://docs.polymarket.com/clob-rest-api")
print()

print(f"Fetching bets for market {MARKET_ID}...")

resp = requests.get(f"https://gamma-api.polymarket.com/markets/{MARKET_ID}")
market = resp.json()

if not market:
    print(f"Market {MARKET_ID} not found")
    exit(1)

market_slug = market.get("slug", "")
market_question = market.get("question", "")
clob_token_ids = market.get("clobTokenIds", [])

if isinstance(clob_token_ids, str):
    import json
    clob_token_ids = json.loads(clob_token_ids)

if not clob_token_ids:
    print(f"No CLOB token IDs found for market {MARKET_ID}")
    exit(1)

outcomes = market.get("outcomes", [])
if isinstance(outcomes, str):
    outcomes = json.loads(outcomes)

all_bets = []

for idx, token_id in enumerate(clob_token_ids):
    outcome_name = outcomes[idx] if idx < len(outcomes) else f"Outcome {idx}"
    
    try:
        book_resp = requests.get(f"https://clob.polymarket.com/book", params={"token_id": token_id}, timeout=10)
        book_resp.raise_for_status()
        book_data = book_resp.json()
    except requests.exceptions.RequestException as e:
        print(f"  Error fetching orderbook for {outcome_name}: {e}")
        continue
    
    if "error" in book_data:
        print(f"  No orderbook for {outcome_name} (token {token_id}): {book_data['error']}")
        continue
    
    bids = book_data.get("bids", [])
    asks = book_data.get("asks", [])
    
    for bid in bids:
        price = float(bid.get("price", 0))
        size = float(bid.get("size", 0))
        usd_amount = price * size
        all_bets.append({
            "market_id": MARKET_ID,
            "market_slug": market_slug,
            "market_question": market_question,
            "outcome": outcome_name,
            "token_id": token_id,
            "side": "buy",
            "price": price,
            "size": size,
            "usd_amount": usd_amount
        })
    
    for ask in asks:
        price = float(ask.get("price", 0))
        size = float(ask.get("size", 0))
        usd_amount = price * size
        all_bets.append({
            "market_id": MARKET_ID,
            "market_slug": market_slug,
            "market_question": market_question,
            "outcome": outcome_name,
            "token_id": token_id,
            "side": "sell",
            "price": price,
            "size": size,
            "usd_amount": usd_amount
        })
    
    print(f"  {outcome_name}: {len(bids)} bids, {len(asks)} asks")

os.makedirs("data", exist_ok=True)
output_file = f"data/bets_{market_slug}_{MARKET_ID}.json"
with open(output_file, "w") as f:
    json.dump(all_bets, f, indent=2)

total_usd = sum(b["usd_amount"] for b in all_bets)
print(f"\nSuccess! Saved {len(all_bets)} bets (${total_usd:,.2f} total) to {output_file}")
