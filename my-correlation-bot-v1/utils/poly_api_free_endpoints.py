#!/usr/bin/env python3

import argparse

from polymarket_template_utils import print_json


ENDPOINTS = {
    "Gamma API": {
        "base_url": "https://gamma-api.polymarket.com",
        "auth": "public",
        "uses": [
            "market and event discovery",
            "tags, series, comments, sports metadata",
            "public profiles and search",
        ],
        "starter_endpoints": [
            "GET /markets",
            "GET /events",
            "GET /markets/slug/{slug}",
            "GET /events/slug/{slug}",
            "GET /search",
            "GET /tags",
            "GET /sports",
        ],
    },
    "Data API": {
        "base_url": "https://data-api.polymarket.com",
        "auth": "public",
        "uses": [
            "wallet activity",
            "positions and PnL",
            "trades, holders, open interest, leaderboards",
        ],
        "starter_endpoints": [
            "GET /activity",
            "GET /positions",
            "GET /trades",
            "GET /holders",
            "GET /value",
            "GET /leaderboard",
        ],
    },
    "CLOB API read endpoints": {
        "base_url": "https://clob.polymarket.com",
        "auth": "public for reads",
        "uses": [
            "orderbook snapshots",
            "best bid/ask prices",
            "midpoints and spreads",
            "tick size and price history",
        ],
        "starter_endpoints": [
            "GET /book?token_id=...",
            "GET /price?token_id=...&side=BUY",
            "GET /midpoint?token_id=...",
            "GET /spread?token_id=...",
            "GET /prices-history?market=...",
        ],
    },
    "CLOB API trading endpoints": {
        "base_url": "https://clob.polymarket.com",
        "auth": "private key plus CLOB API credentials",
        "uses": [
            "place signed orders",
            "list your open orders",
            "cancel your open orders",
            "fetch your own trades",
        ],
        "starter_endpoints": [
            "POST /order",
            "GET /orders",
            "GET /order/{order_id}",
            "DELETE /order",
            "DELETE /orders",
            "DELETE /cancel-all",
        ],
    },
    "CLOB WebSocket": {
        "base_url": "wss://ws-subscriptions-clob.polymarket.com/ws",
        "auth": "market channel public; user channel authenticated",
        "uses": [
            "live orderbook updates",
            "price changes",
            "last trade prices",
            "your own order and trade updates via user channel",
        ],
        "starter_endpoints": [
            "wss://ws-subscriptions-clob.polymarket.com/ws/market",
            "wss://ws-subscriptions-clob.polymarket.com/ws/user",
        ],
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a concise map of free/public Polymarket APIs and trading endpoints.")
    parser.parse_args()
    print_json(ENDPOINTS)


if __name__ == "__main__":
    main()
