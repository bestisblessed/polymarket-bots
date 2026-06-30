#!/usr/bin/env python3

import argparse

from polymarket_template_utils import GAMMA_API, fetch_json, market_summary, market_text, print_json


def fetch_markets(include_closed: bool, page_limit: int, scan_limit: int) -> list[dict]:
    markets = []
    offset = 0
    while len(markets) < scan_limit:
        params = {
            "closed": str(include_closed).lower(),
            "limit": min(page_limit, scan_limit - len(markets)),
            "offset": offset,
        }
        batch = fetch_json(f"{GAMMA_API}/markets", params=params)
        if not isinstance(batch, list) or not batch:
            break
        markets.extend(batch)
        if len(batch) < params["limit"]:
            break
        offset += len(batch)
    return markets


def main() -> None:
    parser = argparse.ArgumentParser(description="Search active Polymarket Gamma markets and print token IDs.")
    parser.add_argument("--query", "-q", help="Case-insensitive text to match against question, slug, category, or description.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum matching markets to print.")
    parser.add_argument("--scan-limit", type=int, default=500, help="Maximum recent Gamma markets to scan.")
    parser.add_argument("--page-limit", type=int, default=100, help="Gamma page size.")
    parser.add_argument("--include-closed", action="store_true", help="Include closed markets in the Gamma request.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    query = (args.query or "").strip().lower()
    matches = []
    for market in fetch_markets(args.include_closed, args.page_limit, args.scan_limit):
        if query and query not in market_text(market):
            continue
        matches.append(market_summary(market))
        if len(matches) >= args.limit:
            break

    if args.json:
        print_json(matches)
        return

    if not matches:
        print("No matching markets found.")
        return

    for index, market in enumerate(matches, 1):
        print(f"{index}. {market['question']}")
        print(f"   slug: {market['slug']}")
        print(f"   condition_id: {market['condition_id']}")
        print(f"   accepting_orders: {market['accepting_orders']}  closed: {market['closed']}")
        print(f"   tick_size: {market['tick_size']}  neg_risk: {market['neg_risk']}")
        for token in market["tokens"]:
            print(f"   token: {token['outcome']}: {token['token_id']}")
        print()


if __name__ == "__main__":
    main()
