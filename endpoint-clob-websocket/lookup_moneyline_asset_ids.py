# Sources (Polymarket Gamma API):
# - https://docs.polymarket.com/developers/gamma-markets-api/overview
# - https://docs.polymarket.com/developers/gamma-markets-api/fetch-markets-guide

import argparse
import json
from typing import Any, List

import requests

BASE_URL = "https://gamma-api.polymarket.com"


def _parse_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return [item.strip() for item in stripped.split(",") if item.strip()]
    return []


def _normalize_slug(value: str) -> str:
    return value.strip().lower()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lookup moneyline asset IDs for a given event slug using the Gamma API."
    )
    parser.add_argument("slug", help="Event slug (e.g. nfl-la-car-2026-01-10)")
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help=f"Gamma API base URL (default: {BASE_URL})",
    )
    args = parser.parse_args()

    slug = _normalize_slug(args.slug)
    url = f"{args.base_url.rstrip('/')}/events/slug/{slug}"

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    payload = response.json()

    markets = payload.get("markets", [])
    moneyline_markets = [
        market for market in markets if market.get("sportsMarketType") == "moneyline"
    ]

    if not moneyline_markets:
        print(f"No moneyline markets found for slug: {slug}")
        return

    for market in moneyline_markets:
        token_ids = (
            _parse_list(market.get("clobTokenIds"))
            or _parse_list(market.get("tokenIds"))
            or _parse_list(market.get("token_ids"))
        )
        outcomes = _parse_list(market.get("outcomes"))
        question = market.get("question") or market.get("title") or ""
        print(f"Market: {question} ({market.get('id', 'unknown')})")
        print(f"Slug: {market.get('slug', 'unknown')}")
        if not token_ids:
            print("  No token IDs found on this market record.")
            continue
        for idx, token_id in enumerate(token_ids):
            outcome = outcomes[idx] if idx < len(outcomes) else "Unknown"
            print(f"  - {outcome}: {token_id}")


if __name__ == "__main__":
    main()
