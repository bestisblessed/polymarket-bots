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

import pandas as pd
import requests

GAMMA_API = "https://gamma-api.polymarket.com/events"
DATA_API = "https://data-api.polymarket.com/holders"

LIMIT_EVENTS = 200
LIMIT_HOLDERS = 50  # fetch more to have enough for per-side tables
MIN_BALANCE = 10

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


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


def fetch_holders_for_market(condition_id):
    try:
        r = requests.get(
            DATA_API,
            params={"market": condition_id, "limit": LIMIT_HOLDERS, "minBalance": MIN_BALANCE},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  Error fetching holders for {condition_id}: {e}")
        return []


def build_holders_data(events):
    rows = []
    fetched_at = datetime.now(timezone.utc).isoformat()
    market_count = 0

    for event in events:
        event_slug = event.get("slug", "")
        event_title = event.get("title", "")
        markets = event.get("markets") or []
        if not markets:
            continue

        for market in markets:
            condition_id = market.get("conditionId")
            if not condition_id:
                continue

            market_question = market.get("question", "")
            market_type = market.get("sportsMarketType", "unknown")

            outcomes = _parse_list(market.get("outcomes") or [])
            prices_raw = _parse_list(market.get("outcomePrices") or [])
            prices = []
            for p in prices_raw:
                try:
                    prices.append(float(p))
                except (ValueError, TypeError):
                    prices.append(None)

            market_count += 1
            print(f"Fetching holders for market {market_count}: {market_question[:50]}...")

            holders_data = fetch_holders_for_market(condition_id)
            for token in holders_data:
                holders = token.get("holders") or []
                if not holders:
                    continue
                for holder in holders:
                    wallet = holder.get("proxyWallet")
                    shares = float(holder.get("amount", 0))
                    if not wallet or not shares:
                        continue
                    outcome_idx = holder.get("outcomeIndex")
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
                    rows.append({
                        "event_slug": event_slug,
                        "event_title": event_title,
                        "market_question": market_question,
                        "market_type": market_type,
                        "conditionId": condition_id,
                        "holder": identity,
                        "wallet": wallet,
                        "outcome": outcome_name,
                        "outcomeIndex": outcome_idx,
                        "shares": shares,
                        "price": price,
                        "approxUsd": approx_usd,
                        "fetched_at": fetched_at,
                    })

    print(f"\nProcessed {market_count} markets, found {len(rows)} holder positions")
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
