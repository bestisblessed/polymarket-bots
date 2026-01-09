import argparse
import json
from typing import Any, List

DEFAULT_DATA_PATH = "data/nfl_games.json"


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


def _base_slug(value: str) -> str:
    base = value
    for marker in ["-spread-", "-total-", "-moneyline-"]:
        if marker in base:
            base = base.split(marker)[0]
    if base.endswith("-moneyline"):
        base = base[: -len("-moneyline")]
    return base


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lookup moneyline asset IDs for a given NFL event slug using data/nfl_games.json."
    )
    parser.add_argument("slug", help="Event slug (e.g. nfl-la-car-2026-01-10)")
    parser.add_argument(
        "--data",
        default=DEFAULT_DATA_PATH,
        help=f"Path to nfl_games.json (default: {DEFAULT_DATA_PATH})",
    )
    args = parser.parse_args()

    slug = _normalize_slug(args.slug)

    with open(args.data, "r", encoding="utf-8") as handle:
        markets = json.load(handle)

    matches = []
    for market in markets:
        if market.get("sportsMarketType") != "moneyline":
            continue
        market_slug = _normalize_slug(str(market.get("slug", "")))
        if not market_slug:
            continue
        if slug not in {_base_slug(market_slug), market_slug}:
            continue
        matches.append(market)

    if not matches:
        print(f"No moneyline markets found for slug: {slug}")
        return

    for market in matches:
        token_ids = (
            _parse_list(market.get("tokenIds"))
            or _parse_list(market.get("token_ids"))
            or _parse_list(market.get("clobTokenIds"))
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
