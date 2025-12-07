import json
import os
import time

import requests


DATA_API = "https://data-api.polymarket.com/holders"
GAMES_FILE = "data/nfl_games.json"
SNAPSHOT_FILE = "data/nfl_holders_snapshot.json"
EVENTS_FILE = "data/large_wagers_events.jsonl"

LIMIT = 200
MIN_BALANCE = 10

# Thresholds for what counts as a "large" wager
MIN_DELTA_SHARES = 1000.0
MIN_DELTA_USD = 500.0


def _parse_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return [value]
    return []


def load_games():
    with open(GAMES_FILE) as f:
        return json.load(f)


def load_snapshot():
    if os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE) as f:
            return json.load(f)
    return {}


def save_snapshot(snapshot):
    os.makedirs("data", exist_ok=True)
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(snapshot, f)


def build_snapshot(games):
    snapshot = {}
    total_holders = 0

    for game in games:
        condition_id = game.get("conditionId")
        if not condition_id:
            continue

        slug = game.get("slug")
        question = game.get("question")

        outcomes = _parse_list(game.get("outcomes") or [])
        prices_raw = _parse_list(game.get("outcomePrices") or [])
        prices = []
        for p in prices_raw:
            if isinstance(p, (int, float, str)):
                prices.append(float(p))

        resp = requests.get(
            DATA_API,
            params={
                "market": condition_id,
                "limit": LIMIT,
                "minBalance": MIN_BALANCE,
            },
            timeout=15,
        )
        payload = resp.json()

        for token in payload:
            holders = token.get("holders") or []
            if not holders:
                continue

            outcome_idx = holders[0].get("outcomeIndex")
            if isinstance(outcome_idx, int) and outcomes and outcome_idx < len(outcomes):
                outcome_name = outcomes[outcome_idx]
            else:
                outcome_name = str(outcome_idx)

            if isinstance(outcome_idx, int) and prices and outcome_idx < len(prices):
                price = float(prices[outcome_idx])
            else:
                price = None

            for holder in holders:
                wallet = holder.get("proxyWallet")
                shares = float(holder.get("amount", 0))
                if not wallet or not shares:
                    continue

                key = f"{condition_id}:{outcome_idx}:{wallet}"
                approx_usd = shares * price if price is not None else None

                snapshot[key] = {
                    "conditionId": condition_id,
                    "slug": slug,
                    "question": question,
                    "outcomeIndex": outcome_idx,
                    "outcome": outcome_name,
                    "wallet": wallet,
                    "shares": shares,
                    "price": price,
                    "approxUsd": approx_usd,
                }
                total_holders += 1

    print(f"Built holder snapshot with {len(snapshot)} unique (market, outcome, wallet) rows")
    print(f"Total holder entries processed: {total_holders}")
    return snapshot


def detect_large_wagers(prev_snapshot, curr_snapshot):
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    events = []

    for key, now in curr_snapshot.items():
        before = prev_snapshot.get(key)
        prev_shares = before["shares"] if before else 0.0
        delta_shares = now["shares"] - prev_shares

        price = now.get("price") or 0.0
        approx_usd = delta_shares * price

        if delta_shares >= MIN_DELTA_SHARES or approx_usd >= MIN_DELTA_USD:
            event = {
                "timestamp": timestamp,
                "conditionId": now["conditionId"],
                "slug": now["slug"],
                "question": now["question"],
                "outcomeIndex": now["outcomeIndex"],
                "outcome": now["outcome"],
                "wallet": now["wallet"],
                "prev_shares": prev_shares,
                "new_shares": now["shares"],
                "delta_shares": delta_shares,
                "price": price,
                "approx_usd": approx_usd,
                "event_type": "holder_delta",
            }
            events.append(event)
            print(
                f"LARGE WAGER: {now['slug']} | {now['outcome']} | "
                f"{now['wallet']} +{delta_shares:.2f} shares (~${approx_usd:.2f})"
            )

    if events:
        os.makedirs("data", exist_ok=True)
        with open(EVENTS_FILE, "a") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        print(f"Recorded {len(events)} large-wager events to {EVENTS_FILE}")
    else:
        print("No large holder deltas detected on this run")


def main():
    print("Note: This script uses Polymarket Data API /holders endpoint")
    print("Docs: https://docs.polymarket.com/api-reference/core/get-top-holders-for-markets")
    print()

    games = load_games()
    print(f"Loaded {len(games)} NFL game markets from {GAMES_FILE}")

    prev_snapshot = load_snapshot()
    if not prev_snapshot:
        print("No previous snapshot found (first run)")

    curr_snapshot = build_snapshot(games)

    if prev_snapshot:
        detect_large_wagers(prev_snapshot, curr_snapshot)
    else:
        print("Skipping detection on first run; saving baseline snapshot only")

    save_snapshot(curr_snapshot)
    print(f"Saved snapshot to {SNAPSHOT_FILE}")


if __name__ == "__main__":
    main()


