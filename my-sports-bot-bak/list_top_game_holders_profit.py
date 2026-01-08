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

                # Potential profit = payout if win ($1 per share) minus current value
                # potential_profit = shares * (1 - price)
                potential_profit = shares * (1 - price) if price is not None else None
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
                        "potentialProfit": potential_profit,
                    }
                )

    df = pd.DataFrame(rows)
    print(f"Built holders table with {len(df)} rows across {len(games)} moneyline markets")
    return df


def print_top_holders(df):
    if df.empty:
        print("No holder data found")
        return

    top = df.dropna(subset=["potentialProfit"])
    top = top.sort_values("potentialProfit", ascending=False).head(TOP_N)

    print(f"\nTop {len(top)} holders by POTENTIAL PROFIT across all NFL moneyline games:\n")
    for i, (_, row) in enumerate(top.iterrows(), start=1):
        odds_pct = row['price'] * 100 if row['price'] else 0
        print(
            f"{i:2d}. ${row['potentialProfit']:,.0f} potential profit "
            f"(${row['approxUsd']:,.0f} position @ {odds_pct:.0f}%) "
            f"| {row['holder'][:20]} "
            f"| {row['outcome']} "
            f"| {row['slug']}"
        )


def main():
    print("Note: This script ranks holders by POTENTIAL PROFIT (shares * (1 - price))")
    print("This highlights sharp underdog bets that would pay big if they win.")
    print()

    games = load_moneyline_games()
    print(f"Loaded {len(games)} NFL moneyline markets from {GAMES_FILE}")

    df = build_holders_df(games)
    print_top_holders(df)


if __name__ == "__main__":
    main()

