import json

import pandas as pd
import requests


DATA_API = "https://data-api.polymarket.com/holders"
GAMES_FILE = "data/nfl_games.json"

LIMIT = 1000
MIN_BALANCE = 10
TOP_N = 50


def _parse_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return [value]
    return []


def load_moneyline_games():
    with open(GAMES_FILE) as f:
        games = json.load(f)
    return [g for g in games if g.get("sportsMarketType") == "moneyline"]


def build_holders_df(games):
    rows = []

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
            },  # Ref: https://docs.polymarket.com/api-reference/core/get-top-holders-for-markets
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
                identity = (
                    holder.get("name")
                    or holder.get("pseudonym")
                    or wallet
                )

                rows.append(
                    {
                        "holder": identity,
                        "wallet": wallet,
                        "conditionId": condition_id,
                        "slug": slug,
                        "question": question,
                        "outcomeIndex": outcome_idx,
                        "outcome": outcome_name,
                        "shares": shares,
                        "price": price,
                        "approxUsd": approx_usd,
                    }
                )

    df = pd.DataFrame(rows)
    print(f"Built holders table with {len(df)} rows across {len(games)} moneyline markets")
    return df


def print_top_holders(df):
    if df.empty:
        print("No holder data found")
        return

    top = df.dropna(subset=["approxUsd"])
    top = top.sort_values("approxUsd", ascending=False).head(TOP_N)

    print(f"\nTop {len(top)} holders across all NFL moneyline games:\n")
    for i, (_, row) in enumerate(top.iterrows(), start=1):
        print(
            f"{i:2d}. ${row['approxUsd']:,.2f} "
            f"| {row['holder']} ({row['wallet']}) "
            f"| Team: {row['outcome']} "
            f"| Game: {row['slug']}"
        )


def main():
    print("Note: This script uses Polymarket Data API /holders endpoint")
    print("Docs: https://docs.polymarket.com/api-reference/core/get-top-holders-for-markets")
    print()

    games = load_moneyline_games()
    print(f"Loaded {len(games)} NFL moneyline markets from {GAMES_FILE}")

    df = build_holders_df(games)
    print_top_holders(df)


if __name__ == "__main__":
    main()


