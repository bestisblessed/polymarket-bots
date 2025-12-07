import json
import os
import time

import pandas as pd
import requests


DATA_API = "https://data-api.polymarket.com/holders"
GAMES_FILE = "data/nfl_games.json"
SNAPSHOT_FILE = "data/nfl_holders_snapshot.csv"
EVENTS_FILE = "data/large_wagers_events.csv"

LIMIT = 1000
MIN_BALANCE = 10

# Threshold for what counts as a "large" holder (by total USD value)
USD_THRESHOLD = 10000.0


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


def detect_large_wagers(prev_df, curr_df):
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
    prev_usd = prev_shares * price
    curr_usd = merged["shares"] * price

    mask = (price > 0) & (prev_usd < USD_THRESHOLD) & (curr_usd >= USD_THRESHOLD)
    alerts = merged[mask].copy()

    if alerts.empty:
        print("No large holder threshold crossings detected on this run")
        return

    alerts["timestamp"] = timestamp
    alerts["prev_shares"] = prev_shares[mask]
    alerts["new_shares"] = alerts["shares"]
    alerts["delta_shares"] = alerts["new_shares"] - alerts["prev_shares"]
    alerts["prev_usd"] = prev_usd[mask]
    alerts["curr_usd"] = curr_usd[mask]
    alerts["threshold_usd"] = USD_THRESHOLD
    alerts["event_type"] = "holder_delta"

    for _, row in alerts.iterrows():
        print(
            f"LARGE HOLDER: {row['slug']} | {row['outcome']} | "
            f"{row['wallet']} crossed ${USD_THRESHOLD:,.0f} "
            f"(prev ~${row['prev_usd']:,.2f} -> now ~${row['curr_usd']:,.2f})"
        )

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
        "prev_usd",
        "curr_usd",
        "threshold_usd",
        "event_type",
    ]
    events_df = alerts[cols]

    os.makedirs("data", exist_ok=True)
    if os.path.exists(EVENTS_FILE):
        events_df.to_csv(EVENTS_FILE, mode="a", header=False, index=False)
    else:
        events_df.to_csv(EVENTS_FILE, index=False)

    print(f"Recorded {len(events_df)} large-holder events to {EVENTS_FILE}")


def main():
    print("Note: This script uses Polymarket Data API /holders endpoint")
    print("Docs: https://docs.polymarket.com/api-reference/core/get-top-holders-for-markets")
    print()

    games = load_games()
    print(f"Loaded {len(games)} NFL game markets from {GAMES_FILE}")

    prev_snapshot_df = load_snapshot()
    if prev_snapshot_df.empty:
        print("No previous snapshot found (first run)")

    curr_snapshot_df = build_snapshot(games)

    detect_large_wagers(prev_snapshot_df, curr_snapshot_df)

    save_snapshot(curr_snapshot_df)
    print(f"Saved snapshot to {SNAPSHOT_FILE}")


if __name__ == "__main__":
    main()


