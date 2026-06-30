#!/usr/bin/env python3

import argparse

from polymarket_template_utils import clob_client, load_clob_sdk, print_json


def call_first(client, method_names: tuple[str, ...], *args):
    for name in method_names:
        method = getattr(client, name, None)
        if method:
            return method(*args)
    joined = ", ".join(method_names)
    raise SystemExit(f"Installed py-clob-client-v2 does not expose any of: {joined}")


def get_orders(client, sdk, args):
    params = {}
    if getattr(args, "market", None):
        params["market"] = args.market
    if getattr(args, "token_id", None):
        params["asset_id"] = args.token_id

    if params and "OpenOrderParams" in sdk:
        try:
            return call_first(client, ("get_open_orders", "get_orders", "getOpenOrders"), sdk["OpenOrderParams"](**params))
        except TypeError:
            pass
    if params:
        try:
            return call_first(client, ("get_open_orders", "get_orders", "getOpenOrders"), params)
        except TypeError:
            pass
    return call_first(client, ("get_open_orders", "get_orders", "getOpenOrders"))


def main() -> None:
    parser = argparse.ArgumentParser(description="List/get/cancel authenticated Polymarket CLOB orders.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List open orders.")
    list_parser.add_argument("--market", help="Optional market condition ID filter.")
    list_parser.add_argument("--token-id", help="Optional CLOB token ID filter.")

    get_parser = subparsers.add_parser("get", help="Get one order by ID.")
    get_parser.add_argument("--order-id", required=True)

    cancel_parser = subparsers.add_parser("cancel", help="Cancel one order by ID.")
    cancel_parser.add_argument("--order-id", required=True)
    cancel_parser.add_argument("--live", action="store_true", help="Actually cancel the order.")

    cancel_all_parser = subparsers.add_parser("cancel-all", help="Cancel all open orders.")
    cancel_all_parser.add_argument("--live", action="store_true", help="Actually cancel all open orders.")

    cancel_market_parser = subparsers.add_parser("cancel-market", help="Cancel open orders by condition ID or token ID.")
    cancel_market_parser.add_argument("--market", help="Market condition ID.")
    cancel_market_parser.add_argument("--token-id", help="CLOB token ID / asset ID.")
    cancel_market_parser.add_argument("--live", action="store_true", help="Actually cancel matching open orders.")

    args = parser.parse_args()

    if args.command == "list":
        sdk = load_clob_sdk()
        client = clob_client(require_creds=True)
        print_json(get_orders(client, sdk, args))
        return
    if args.command == "get":
        client = clob_client(require_creds=True)
        print_json(call_first(client, ("get_order", "getOrder"), args.order_id))
        return
    if args.command == "cancel":
        if not args.live:
            print_json({"mode": "PREVIEW", "action": "cancel", "order_id": args.order_id})
            print("Preview only. Add --live to cancel this order.")
            return
        sdk = load_clob_sdk()
        client = clob_client(require_creds=True)
        print_json(call_first(client, ("cancel_order", "cancelOrder"), sdk["OrderPayload"](orderID=args.order_id)))
        return
    if args.command == "cancel-all":
        if not args.live:
            print_json({"mode": "PREVIEW", "action": "cancel-all"})
            print("Preview only. Add --live to cancel all open orders.")
            return
        client = clob_client(require_creds=True)
        print_json(call_first(client, ("cancel_all", "cancelAll")))
        return
    if args.command == "cancel-market":
        if not args.market and not args.token_id:
            raise SystemExit("Provide --market or --token-id.")
        payload = {}
        if args.market:
            payload["market"] = args.market
        if args.token_id:
            payload["asset_id"] = args.token_id
        if not args.live:
            print_json({"mode": "PREVIEW", "action": "cancel-market", "payload": payload})
            print("Preview only. Add --live to cancel matching open orders.")
            return
        sdk = load_clob_sdk()
        client = clob_client(require_creds=True)
        print_json(call_first(client, ("cancel_market_orders", "cancelMarketOrders"), sdk["OrderMarketCancelParams"](**payload)))


if __name__ == "__main__":
    main()
