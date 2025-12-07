import json
import os

import requests

DATA_API = "https://data-api.polymarket.com/trades"
GAMES_FILE = "data/nfl_games.json"
OUTPUT_DIR = "data/game-bets"
LIMIT = 1000

with open(GAMES_FILE) as f:
    games = json.load(f)

os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_trades(event_id):
    trades = []
    offset = 0
    while True:
        resp = requests.get(
            DATA_API,
            params={
                "eventId": event_id,
                "limit": LIMIT,
                "offset": offset,
                "takerOnly": True,
            },  # Ref: https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets
            timeout=10,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        trades.extend(batch)
        if len(batch) < LIMIT:
            break
        offset += LIMIT
    return trades


for game in games:
    event = (game.get("events") or [{}])[0]
    event_id = event.get("id")
    if not event_id:
        continue
    slug = game["slug"]
    trades = fetch_trades(event_id)
    total_usdc = sum(
        float(t.get("size", 0)) * float(t.get("price", 0)) for t in trades
    )
    out_path = f"{OUTPUT_DIR}/{slug}.json"
    with open(out_path, "w") as f:
        json.dump(
            {
                "slug": slug,
                "eventId": event_id,
                "question": game.get("question"),
                "tradeCount": len(trades),
                "totalUsdc": total_usdc,
                "trades": trades,
            },
            f,
            indent=2,
        )
    print(f"{slug}: {len(trades)} trades (${total_usdc:.2f} USDC)")
