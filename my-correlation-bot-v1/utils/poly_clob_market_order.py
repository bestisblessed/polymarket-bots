#!/usr/bin/env python3

import argparse

from polymarket_template_utils import (
    clob_client,
    enum_value,
    fetch_token_options,
    load_clob_sdk,
    parse_bool,
    print_json,
)


def preview_payload(args, options: dict) -> dict:
    amount_unit = "USDC/pUSD spend" if args.side == "BUY" else "shares to sell"
    return {
        "mode": "LIVE" if args.live else "PREVIEW",
        "order_kind": "market",
        "token_id": args.token_id,
        "side": args.side,
        "amount": args.amount,
        "amount_unit": amount_unit,
        "worst_price": args.worst_price,
        "order_type": args.type,
        "tick_size": options["tick_size"],
        "neg_risk": options["neg_risk"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview or place a Polymarket CLOB market-style order.")
    parser.add_argument("--token-id", required=True, help="CLOB token ID / asset ID from Gamma clobTokenIds.")
    parser.add_argument("--side", required=True, choices=["BUY", "SELL"], help="Order side.")
    parser.add_argument("--amount", required=True, type=float, help="BUY: USDC/pUSD amount. SELL: share amount.")
    parser.add_argument("--worst-price", required=True, type=float, help="Worst acceptable execution price.")
    parser.add_argument("--type", default="FOK", choices=["FOK", "FAK"], help="Immediate execution order type.")
    parser.add_argument("--tick-size", help="Override market tick size. Defaults to /book tick_size or 0.01.")
    parser.add_argument("--neg-risk", choices=["true", "false"], help="Override neg risk flag.")
    parser.add_argument("--live", action="store_true", help="Actually submit the order. Omit for preview mode.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    options = fetch_token_options(
        args.token_id,
        tick_size=args.tick_size,
        neg_risk=parse_bool(args.neg_risk) if args.neg_risk is not None else None,
    )
    payload = preview_payload(args, options)

    if not args.live:
        print_json(payload)
        print("Preview only. Add --live to submit this order.")
        return

    sdk = load_clob_sdk()
    client = clob_client(require_creds=True)
    side = enum_value(sdk["Side"], args.side)
    order_type = enum_value(sdk["OrderType"], args.type)
    try:
        order_args = sdk["MarketOrderArgs"](
            token_id=args.token_id,
            amount=args.amount,
            side=side,
            price=args.worst_price,
            order_type=order_type,
        )
    except TypeError:
        order_args = sdk["MarketOrderArgs"](
            token_id=args.token_id,
            amount=args.amount,
            side=side,
            price=args.worst_price,
        )
    order_options = sdk["PartialCreateOrderOptions"](
        tick_size=str(options["tick_size"]),
        neg_risk=bool(options["neg_risk"]),
    )

    print_json(payload)
    response = client.create_and_post_market_order(
        order_args=order_args,
        options=order_options,
        order_type=order_type,
    )
    print_json({"response": response})


if __name__ == "__main__":
    main()
