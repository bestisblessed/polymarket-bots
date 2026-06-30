#!/usr/bin/env python3

import argparse
from typing import Any

from polymarket_template_utils import clob_get, print_json


def safe_clob_get(label: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        return {"ok": True, "label": label, "data": clob_get(path, params)}
    except Exception as exc:
        return {"ok": False, "label": label, "error": str(exc)}


def compact_book(book: dict[str, Any], depth: int) -> dict[str, Any]:
    data = dict(book)
    for side in ("bids", "asks"):
        levels = data.get(side)
        if isinstance(levels, list):
            data[side] = levels[:depth]
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch public CLOB price, midpoint, spread, and optional orderbook data.")
    parser.add_argument("--token-id", required=True, help="CLOB token ID / asset ID from Gamma clobTokenIds.")
    parser.add_argument("--side", choices=["BUY", "SELL"], help="Only fetch one side's best executable price.")
    parser.add_argument("--book", action="store_true", help="Include the orderbook.")
    parser.add_argument("--depth", type=int, default=5, help="Orderbook levels to print per side.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    token_params = {"token_id": args.token_id}
    results = {
        "token_id": args.token_id,
        "midpoint": safe_clob_get("midpoint", "midpoint", token_params),
        "spread": safe_clob_get("spread", "spread", token_params),
        "prices": {},
    }
    sides = [args.side] if args.side else ["BUY", "SELL"]
    for side in sides:
        results["prices"][side] = safe_clob_get("price", "price", {"token_id": args.token_id, "side": side})

    if args.book:
        book_result = safe_clob_get("book", "book", token_params)
        if book_result["ok"] and isinstance(book_result.get("data"), dict):
            book_result["data"] = compact_book(book_result["data"], args.depth)
        results["book"] = book_result

    if args.json:
        print_json(results)
        return

    print(f"token_id: {args.token_id}")
    midpoint = results["midpoint"]
    print(f"midpoint: {midpoint.get('data') if midpoint['ok'] else midpoint.get('error')}")
    spread = results["spread"]
    print(f"spread: {spread.get('data') if spread['ok'] else spread.get('error')}")
    for side, price in results["prices"].items():
        print(f"{side.lower()} price: {price.get('data') if price['ok'] else price.get('error')}")
    if "book" in results:
        print("book:")
        print_json(results["book"])


if __name__ == "__main__":
    main()
