import json
import os
import time

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

DATA_API = "https://data-api.polymarket.com/holders"
GAMES_FILE = "data/nfl_games.json"
SNAPSHOT_FILE = "data/nfl_holders_profit_snapshot.csv"
EVENTS_FILE = "data/large_profit_events.csv"
PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json"

LIMIT = 1000
MIN_BALANCE = 10

# Threshold for what counts as a "large" potential profit position
PROFIT_THRESHOLD = 40000.0


def send_pushover(message: str, url: str = None) -> None:
    token = os.environ.get("PUSHOVER_API_TOKEN")
    user = os.environ.get("PUSHOVER_GROUP_KEY")
    if not token or not user:
        print("Pushover credentials not found in .env, skipping notification")
        return
    data = {"token": token, "user": user, "message": message, "html": 1}
    if url:
        data["url"] = url
        data["url_title"] = "View Profile"
    resp = requests.post(PUSHOVER_ENDPOINT, data=data, timeout=10)
    if resp.ok:
        print("Pushover notification sent")
    else:
        print(f"Pushover failed: {resp.status_code}")


def extract_game_from_slug(slug: str) -> str:
    """Extract game matchup from slug like 'nfl-sea-atl-2025-12-07' -> 'SEA @ ATL'."""
    parts = slug.replace("nfl-", "").split("-")
    if len(parts) >= 2:
        return f"{parts[0].upper()} @ {parts[1].upper()}"
    return ""


def format_bet_line(slug: str, outcome: str, price: float) -> str:
    """Extract spread/total line from slug and format with odds."""
    odds_pct = int(price * 100)
    game = extract_game_from_slug(slug)
    
    if "-spread-" in slug:
        parts = slug.split("-spread-")[-1]
        line = parts.split("-")[-1].replace("pt", ".")
        return f"{outcome} +{line} ({odds_pct}%)"
    elif "-total-" in slug:
        parts = slug.split("-total-")[-1]
        direction = "Over" if "over" in parts else "Under"
        line = parts.split("-")[-1].replace("pt", ".")
        return f"{game} {direction} {line} ({odds_pct}%)"
    else:
        return f"{outcome} ML ({odds_pct}%)"  # moneyline


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
        return pd.read_csv(SNAPSHOT_FILE)
    return pd.DataFrame([])


def save_snapshot(df):
    os.makedirs("data", exist_ok=True)
    df.to_csv(SNAPSHOT_FILE, index=False)


def build_snapshot(games):
    rows = []
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

                # Potential profit = payout if win minus current value
                potential_profit = shares * (1 - price) if price is not None else None
                approx_usd = shares * price if price is not None else None

                rows.append(
                    {
                        "conditionId": condition_id,
                        "slug": slug,
                        "question": question,
                        "outcomeIndex": outcome_idx,
                        "outcome": outcome_name,
                        "wallet": wallet,
                        "shares": shares,
                        "price": price,
                        "approxUsd": approx_usd,
                        "potentialProfit": potential_profit,
                    }
                )
                total_holders += 1

    df = pd.DataFrame(rows)
    print(
        f"Built holder snapshot with {len(df)} rows "
        "(one per (market, outcome, wallet))"
    )
    print(f"Total holder entries processed: {total_holders}")
    return df


def detect_large_profit_positions(prev_df, curr_df):
    if prev_df.empty:
        print("No previous snapshot for comparison; skipping detection")
        return

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    merged = curr_df.merge(
        prev_df,
        on=["conditionId", "outcomeIndex", "wallet"],
        how="left",
        suffixes=("", "_prev"),
    )

    prev_shares = merged["shares_prev"].fillna(0.0)
    price = merged["price"].fillna(0.0)
    
    # Calculate potential profit: shares * (1 - price)
    prev_profit = prev_shares * (1 - price)
    curr_profit = merged["shares"] * (1 - price)

    mask = (price > 0) & (price < 1) & (prev_profit < PROFIT_THRESHOLD) & (curr_profit >= PROFIT_THRESHOLD)
    alerts = merged[mask].copy()

    if alerts.empty:
        print("No large potential profit threshold crossings detected on this run")
        return

    alerts["timestamp"] = timestamp
    alerts["prev_shares"] = prev_shares[mask]
    alerts["new_shares"] = alerts["shares"]
    alerts["delta_shares"] = alerts["new_shares"] - alerts["prev_shares"]
    alerts["prev_profit"] = prev_profit[mask]
    alerts["curr_profit"] = curr_profit[mask]
    alerts["threshold_profit"] = PROFIT_THRESHOLD
    alerts["event_type"] = "profit_threshold"

    for _, row in alerts.iterrows():
        bet_line = format_bet_line(row['slug'], row['outcome'], row['price'])
        position_val = row['new_shares'] * row['price']
        potential_profit = row['curr_profit']
        profile_url = f"https://polymarket.com/profile/{row['wallet']}"
        
        msg = (
            f"LARGE WAGER PLACED:\n\n"
            f"{bet_line}\n"
            f"${position_val:,.0f} to win ${potential_profit:,.0f}\n"
            f"{profile_url}"
        )
        print(msg)
        send_pushover(msg, profile_url)

    cols = [
        "timestamp",
        "conditionId",
        "slug",
        "question",
        "outcomeIndex",
        "outcome",
        "wallet",
        "prev_shares",
        "new_shares",
        "delta_shares",
        "price",
        "prev_profit",
        "curr_profit",
        "threshold_profit",
        "event_type",
    ]
    events_df = alerts[cols]

    os.makedirs("data", exist_ok=True)
    if os.path.exists(EVENTS_FILE):
        events_df.to_csv(EVENTS_FILE, mode="a", header=False, index=False)
    else:
        events_df.to_csv(EVENTS_FILE, index=False)

    print(f"Recorded {len(events_df)} large-profit events to {EVENTS_FILE}")


def main():
    print("Note: This script monitors POTENTIAL PROFIT (shares * (1 - price))")
    print(f"Alerts when a holder crosses ${PROFIT_THRESHOLD:,.0f} potential profit")
    print("This catches sharp underdog bets that would pay big if they win.")
    print()

    games = load_games()
    print(f"Loaded {len(games)} NFL game markets from {GAMES_FILE}")

    prev_snapshot_df = load_snapshot()
    if prev_snapshot_df.empty:
        print("No previous snapshot found (first run)")

    curr_snapshot_df = build_snapshot(games)

    detect_large_profit_positions(prev_snapshot_df, curr_snapshot_df)

    save_snapshot(curr_snapshot_df)
    print(f"Saved snapshot to {SNAPSHOT_FILE}")


if __name__ == "__main__":
    main()

