import json
import os
import sys

import requests

DATA_API = "https://data-api.polymarket.com/trades"
GAMES_FILE = "data/nfl_games.json"
OUTPUT_DIR = "data/game-bets"
LIMIT = 1000

with open(GAMES_FILE) as f:
    games = json.load(f)

target = sys.argv[1] if len(sys.argv) > 1 else games[0]["slug"]
getter = (
    lambda game: game.get("slug") == target
    or (game.get("events") and game["events"][0].get("id") == target)
)

game = next((g for g in games if getter(g)), None)
if not game:
    raise SystemExit(f"Game '{target}' not in {GAMES_FILE}")

event = (game.get("events") or [{}])[0]
event_id = event.get("id")
if not event_id:
    raise SystemExit(f"Game '{game['slug']}' missing event id")

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

total_usdc = sum(
    float(t.get("size", 0)) * float(t.get("price", 0)) for t in trades
)

os.makedirs(OUTPUT_DIR, exist_ok=True)
out_path = f"{OUTPUT_DIR}/{game['slug']}.json"

with open(out_path, "w") as f:
    json.dump(
        {
            "slug": game["slug"],
            "eventId": event_id,
            "question": game.get("question"),
            "tradeCount": len(trades),
            "totalUsdc": total_usdc,
            "trades": trades,
        },
        f,
        indent=2,
    )

print(
    f"Saved {len(trades)} trades (${total_usdc:.2f} USDC) "
    f"for {game['slug']} -> {out_path}"
)
