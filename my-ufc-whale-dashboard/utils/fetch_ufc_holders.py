#!/usr/bin/env python3
"""
Fetch UFC holders and save to CSV (scrape-only).

This script:
  - pulls active UFC events with moneyline markets
  - fetches top holders for every market in those events (all market types)
  - saves a timestamped CSV with holder rows; no P&L calculations or tables here

Use `report_ufc_holders.py` to compute Account P&L / UFC P&L and print tables.
"""

import json
import os
from datetime import datetime, timezone
from typing import Callable

import pandas as pd
import requests

GAMMA_API = "https://gamma-api.polymarket.com/events"
DATA_API = "https://data-api.polymarket.com/holders"

LIMIT_EVENTS = 200
LIMIT_HOLDERS = 20  # Data API maximum per token
MIN_BALANCE = 10
HOLDER_BATCH_SIZE = 20

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def _parse_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return [value]
    return []


def fetch_ufc_fight_events():
    offset = 0
    fight_events = []
    while True:
        r = requests.get(
            GAMMA_API,
            params={
                "tag_slug": "ufc",
                "active": "true",
                "closed": "false",
                "archived": "false",
                "limit": LIMIT_EVENTS,
                "offset": offset,
            },
            headers={"User-Agent": "curl/8.0"},
            timeout=60,
        )
        r.raise_for_status()
        events = r.json() or []
        if not events:
            break
        for ev in events:
            markets = ev.get("markets") or []
            if not markets:
                continue
            has_moneyline = any((m.get("sportsMarketType") or "") == "moneyline" for m in markets)
            if has_moneyline:
                fight_events.append(ev)
        offset += len(events)
    print(f"Fetched {len(fight_events)} UFC fight events (with moneyline markets)")
    return fight_events


def _chunks(items, size):
    for idx in range(0, len(items), size):
        yield items[idx:idx + size]


def _market_info(event, market):
    outcomes = _parse_list(market.get("outcomes") or [])
    prices_raw = _parse_list(market.get("outcomePrices") or [])
    prices = []
    for p in prices_raw:
        try:
            prices.append(float(p))
        except (ValueError, TypeError):
            prices.append(None)

    return {
        "event_slug": event.get("slug", ""),
        "event_title": event.get("title", ""),
        "market_question": market.get("question", ""),
        "market_type": market.get("sportsMarketType", "unknown"),
        "conditionId": market.get("conditionId"),
        "outcomes": outcomes,
        "prices": prices,
        "clobTokenIds": _parse_list(market.get("clobTokenIds") or []),
    }


def _collect_market_infos(events):
    market_infos = []
    token_lookup = {}
    for event in events:
        for market in event.get("markets") or []:
            condition_id = market.get("conditionId")
            if not condition_id:
                continue

            info = _market_info(event, market)
            market_infos.append(info)
            for idx, token_id in enumerate(info["clobTokenIds"]):
                token_lookup[str(token_id)] = (info, idx)

    return market_infos, token_lookup


def fetch_holders_for_markets(condition_ids):
    if not condition_ids:
        return []
    try:
        r = requests.get(
            DATA_API,
            params={
                "market": ",".join(condition_ids),
                "limit": LIMIT_HOLDERS,
                "minBalance": MIN_BALANCE,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"  Error fetching holders for {len(condition_ids)} markets: {e}")
        is_forbidden = (
            isinstance(e, requests.HTTPError)
            and e.response is not None
            and e.response.status_code == 403
        )
        if is_forbidden and len(condition_ids) > 1:
            midpoint = len(condition_ids) // 2
            print("  Retrying failed holders batch as smaller requests...")
            return (
                fetch_holders_for_markets(condition_ids[:midpoint])
                + fetch_holders_for_markets(condition_ids[midpoint:])
            )
        return []


def fetch_holders_for_market(condition_id):
    return fetch_holders_for_markets([condition_id])


def _holder_row(info, holder, fallback_outcome_idx, fetched_at):
    wallet = holder.get("proxyWallet")
    try:
        shares = float(holder.get("amount", 0))
    except (TypeError, ValueError):
        shares = 0.0
    if not wallet or not shares:
        return None

    outcome_idx = holder.get("outcomeIndex")
    if not isinstance(outcome_idx, int):
        outcome_idx = fallback_outcome_idx

    outcomes = info["outcomes"]
    prices = info["prices"]
    if isinstance(outcome_idx, int) and outcomes and outcome_idx < len(outcomes):
        outcome_name = outcomes[outcome_idx]
    else:
        outcome_name = str(outcome_idx)
    if isinstance(outcome_idx, int) and prices and outcome_idx < len(prices) and prices[outcome_idx] is not None:
        price = prices[outcome_idx]
        approx_usd = shares * price
    else:
        price = None
        approx_usd = None

    identity = holder.get("name") or holder.get("pseudonym") or wallet
    return {
        "event_slug": info["event_slug"],
        "event_title": info["event_title"],
        "market_question": info["market_question"],
        "market_type": info["market_type"],
        "conditionId": info["conditionId"],
        "holder": identity,
        "wallet": wallet,
        "outcome": outcome_name,
        "outcomeIndex": outcome_idx,
        "shares": shares,
        "price": price,
        "approxUsd": approx_usd,
        "fetched_at": fetched_at,
    }


def build_holders_data(
    events,
    batch_size=HOLDER_BATCH_SIZE,
    fetcher: Callable[[list[str]], list[dict]] = fetch_holders_for_markets,
):
    rows = []
    fetched_at = datetime.now(timezone.utc).isoformat()

    market_infos, token_lookup = _collect_market_infos(events)
    condition_ids = [info["conditionId"] for info in market_infos]

    for batch_idx, condition_batch in enumerate(_chunks(condition_ids, batch_size), start=1):
        first = ((batch_idx - 1) * batch_size) + 1
        last = first + len(condition_batch) - 1
        print(f"Fetching holders for markets {first}-{last} of {len(condition_ids)}...")

        holders_data = fetcher(condition_batch)
        fallback_info = None
        if len(condition_batch) == 1:
            fallback_info = next((info for info in market_infos if info["conditionId"] == condition_batch[0]), None)

        for token in holders_data:
            token_id = str(token.get("token", ""))
            if token_id in token_lookup:
                info, fallback_outcome_idx = token_lookup[token_id]
            elif fallback_info is not None:
                info, fallback_outcome_idx = fallback_info, None
            else:
                print(f"  Warning: No market metadata found for holder token {token_id}")
                continue

            for holder in token.get("holders") or []:
                row = _holder_row(info, holder, fallback_outcome_idx, fetched_at)
                if row:
                    rows.append(row)

    print(f"\nProcessed {len(condition_ids)} markets, found {len(rows)} holder positions")
    return rows


def save_to_csv(rows):
    os.makedirs(DATA_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"ufc_holders_{timestamp}.csv"
    filepath = os.path.join(DATA_DIR, filename)
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("approxUsd", ascending=False, na_position="last")
    df.to_csv(filepath, index=False)
    print(f"Saved {len(df)} rows to {filepath}")
    return filepath


def main():
    print("UFC Whale Dashboard - Fetch Holders (scrape only)")
    print("=" * 60)
    events = fetch_ufc_fight_events()
    if not events:
        print("No active UFC events found")
        return
    rows = build_holders_data(events)
    if not rows:
        print("No holder data found")
        return
    save_to_csv(rows)


if __name__ == "__main__":
    main()
