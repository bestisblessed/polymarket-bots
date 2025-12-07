import requests
import json
import os
from datetime import datetime
import pytz

NFL_GAME_TAG_ID = "100639"
all_markets = []
offset = 0
limit = 100

print("Fetching NFL game markets (spreads, totals, moneylines)...")
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

# Save json
os.makedirs("data", exist_ok=True)
with open("data/nfl_games.json", "w") as f:
    json.dump(markets_list, f, indent=2)
print(f"\nSuccess! Saved {len(markets_list)} NFL game markets to 'data/nfl_games.json'")

# Print games
unique_games = {}
for m in markets_list:
    if m.get("sportsMarketType") != "moneyline":
        continue
    slug = m.get("slug", "")
    if not slug:
        continue
    base_slug = slug.split("-spread-")[0].split("-total-")[0]
    if base_slug not in unique_games:
        game_name = m.get("question", "")
        if not game_name and m.get("events"):
            game_name = m.get("events", [{}])[0].get("title", "")
        game_id = m.get("id")
        if not game_id and m.get("events"):
            game_id = m.get("events", [{}])[0].get("id", "")
        start_time = m.get("gameStartTime") or m.get("endDate")
        if not start_time and m.get("events"):
            start_time = m.get("events", [{}])[0].get("startTime") or m.get("events", [{}])[0].get("endDate")
        unique_games[base_slug] = {
            "name": game_name,
            "slug": base_slug,
            "id": game_id,
            "start_time": start_time
        }
games_list = sorted(unique_games.values(), key=lambda x: x["start_time"] or "")

# Print games
print(f"\nUpcoming games ({len(games_list)}):")
for game in games_list:
    game_name = game["name"]
    slug = game["slug"]
    game_id = game["id"]
    time_str = ""
    if game["start_time"]:
        try:
            dt = datetime.fromisoformat(game["start_time"].replace("Z", "+00:00"))
            dt_utc = dt.replace(tzinfo=pytz.UTC)
            dt_et = dt_utc.astimezone(pytz.timezone("America/New_York"))
            time_str = dt_et.strftime("%m/%d/%y @ %-I%p").lower()
        except:
            time_str = game["start_time"]
    print(f"- {game_name} - {slug} ({game_id}) - {time_str}")
