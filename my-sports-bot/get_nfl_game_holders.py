import json
import os

import requests

DATA_API = "https://data-api.polymarket.com/holders"
GAMES_FILE = "data/nfl_games.json"
OUTPUT_DIR = "data/game-holders"
LIMIT = 200
MIN_BALANCE = 10


def _parse_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return [value]
    return []


with open(GAMES_FILE) as f:
    games = json.load(f)

moneyline_games = [
    g for g in games if g.get("sportsMarketType") == "moneyline"
]
os.makedirs(OUTPUT_DIR, exist_ok=True)

for game in moneyline_games:
    condition_id = game.get("conditionId")
    if not condition_id:
        continue
    slug = game.get("slug")
    outcomes = _parse_list(game.get("outcomes") or [])
    prices = [
        float(p) for p in _parse_list(game.get("outcomePrices") or [])
        if isinstance(p, (int, float, str))
    ]
    resp = requests.get(
        DATA_API,
        params={
            "market": condition_id,
            "limit": LIMIT,
            "minBalance": MIN_BALANCE,
        },  # Ref: https://docs.polymarket.com/api-reference/core/get-top-holders-for-markets
        timeout=15,
    )
    resp.raise_for_status()
    payload = resp.json()
    holders_summary = []
    for token in payload:
        holders = token.get("holders") or []
        outcome_idx = None
        if holders:
            outcome_idx = holders[0].get("outcomeIndex")
        outcome_name = (
            outcomes[outcome_idx]
            if isinstance(outcome_idx, int)
            and outcomes
            and outcome_idx < len(outcomes)
            else str(outcome_idx)
        )
        price = (
            float(prices[outcome_idx])
            if isinstance(outcome_idx, int)
            and prices
            and outcome_idx < len(prices)
            else None
        )
        for holder in holders:
            shares = float(holder.get("amount", 0))
            approx_usd = shares * price if price is not None else None
            identity = (
                holder.get("name")
                or holder.get("pseudonym")
                or holder.get("proxyWallet")
            )
            holders_summary.append(
                {
                    "holder": identity,
                    "proxyWallet": holder.get("proxyWallet"),
                    "outcome": outcome_name,
                    "outcomeIndex": outcome_idx,
                    "shares": shares,
                    "approxUsd": approx_usd,
                }
            )
    holders_summary.sort(key=lambda h: h.get("shares", 0), reverse=True)
    out_path = f"{OUTPUT_DIR}/{slug}.json"
    with open(out_path, "w") as f:
        json.dump(
            {
                "slug": slug,
                "conditionId": condition_id,
                "question": game.get("question"),
                "holders": holders_summary,
            },
            f,
            indent=2,
        )
    print(f"{slug}: saved {len(holders_summary)} holder rows -> {out_path}")
