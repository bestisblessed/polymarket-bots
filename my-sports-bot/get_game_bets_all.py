import requests
import json
import os

print("Note: This script uses the Polymarket CLOB API /book endpoint")
print("Documentation: https://docs.polymarket.com/clob-rest-api")
print()

NFL_GAME_TAG_ID = "100639"
all_markets = []
offset = 0
limit = 100

print("Fetching NFL game markets...")
while True:
    params = {
        "tag_id": NFL_GAME_TAG_ID,
        "closed": "false",
        "limit": limit,
        "offset": offset,
    }
    resp = requests.get("https://gamma-api.polymarket.com/markets", params=params)
    batch = resp.json()
    if not batch:
        break
    for m in batch:
        if m.get("sportsMarketType") not in ["spreads", "totals", "moneyline"]:
            continue
        slug = m.get("slug", "").lower()
        events = m.get("events", [])
        is_nfl = False
        if slug.startswith("nfl-"):
            is_nfl = True
        elif events:
            for event in events:
                series_slug = event.get("seriesSlug", "").lower()
                if "nfl" in series_slug:
                    is_nfl = True
                    break
        if is_nfl:
            all_markets.append(m)
    if len(batch) < limit:
        break
    offset += limit

unique_markets = {}
for m in all_markets:
    mid = m.get("id")
    if mid is not None:
        unique_markets[mid] = m
markets_list = list(unique_markets.values())

print(f"Found {len(markets_list)} NFL game markets")
print("Fetching bets for each market...\n")

all_bets = []
markets_processed = 0
markets_with_bets = 0

for market in markets_list:
    market_id = market.get("id")
    market_slug = market.get("slug", "")
    market_question = market.get("question", "")
    clob_token_ids = market.get("clobTokenIds", [])
    
    if isinstance(clob_token_ids, str):
        clob_token_ids = json.loads(clob_token_ids)
    
    if not clob_token_ids:
        continue
    
    outcomes = market.get("outcomes", [])
    if isinstance(outcomes, str):
        outcomes = json.loads(outcomes)
    
    market_bets = []
    
    for idx, token_id in enumerate(clob_token_ids):
        outcome_name = outcomes[idx] if idx < len(outcomes) else f"Outcome {idx}"
        
        try:
            book_resp = requests.get(f"https://clob.polymarket.com/book", params={"token_id": token_id}, timeout=10)
            book_resp.raise_for_status()
            book_data = book_resp.json()
        except requests.exceptions.RequestException:
            continue
        
        if "error" in book_data:
            continue
        
        bids = book_data.get("bids", [])
        asks = book_data.get("asks", [])
        
        for bid in bids:
            price = float(bid.get("price", 0))
            size = float(bid.get("size", 0))
            usd_amount = price * size
            market_bets.append({
                "market_id": market_id,
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
            market_bets.append({
                "market_id": market_id,
                "market_slug": market_slug,
                "market_question": market_question,
                "outcome": outcome_name,
                "token_id": token_id,
                "side": "sell",
                "price": price,
                "size": size,
                "usd_amount": usd_amount
            })
    
    if market_bets:
        markets_with_bets += 1
        all_bets.extend(market_bets)
        print(f"  {market_slug}: {len(market_bets)} bets")
    
    markets_processed += 1
    if markets_processed % 10 == 0:
        print(f"Processed {markets_processed}/{len(markets_list)} markets...")

os.makedirs("data", exist_ok=True)
output_file = "data/nfl_game_bets_all.json"
with open(output_file, "w") as f:
    json.dump(all_bets, f, indent=2)

total_usd = sum(b["usd_amount"] for b in all_bets)
print(f"\nSuccess! Processed {markets_processed} markets, {markets_with_bets} with bets")
print(f"Saved {len(all_bets)} total bets (${total_usd:,.2f} total) to {output_file}")
