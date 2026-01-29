#!/usr/bin/env python3
"""
Fetch UFC holders and save to CSV (scrape-only).

This script:
  - pulls active UFC events with moneyline markets
  - fetches top holders for every market in those events (all market types)
  - fetches all-trades stats per market (Data API /trades)
  - saves timestamped CSVs with holder rows and trade stats; no P&L here

Use `report_ufc_holders.py` to compute Account P&L / UFC P&L and print tables.
"""

import json
import os
from datetime import datetime, timezone

import pandas as pd
import requests

GAMMA_API = "https://gamma-api.polymarket.com/events"
DATA_API = "https://data-api.polymarket.com/holders"
TRADES_API = "https://data-api.polymarket.com/trades"

LIMIT_EVENTS = 200
# /holders returns top holders only. Limit is capped (docs show max 20).
HOLDERS_LIMIT = 20
HOLDERS_MIN_BALANCE = 10

# /trades supports pagination with limit/offset.
TRADES_PAGE_LIMIT = 1000
TRADES_MAX_OFFSET = 10000
TRADES_TAKER_ONLY = True

FETCH_TRADE_STATS = os.getenv("UFC_FETCH_TRADES", "1").strip().lower() in ("1", "true", "yes", "y")
MAX_MARKETS = os.getenv("UFC_MAX_MARKETS")
try:
    MAX_MARKETS = int(MAX_MARKETS) if MAX_MARKETS else None
except ValueError:
    MAX_MARKETS = None

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


def fetch_holders_for_market(condition_id):
    try:
        r = requests.get(
            DATA_API,
            params={"market": condition_id, "limit": HOLDERS_LIMIT, "minBalance": HOLDERS_MIN_BALANCE},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  Error fetching holders for {condition_id}: {e}")
        return []


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _trade_outcome(trade, outcomes):
    outcome = trade.get("outcome")
    if isinstance(outcome, str) and outcome:
        return outcome
    outcome_idx = trade.get("outcomeIndex")
    if isinstance(outcome_idx, int) and outcomes and outcome_idx < len(outcomes):
        return outcomes[outcome_idx]
    if outcome_idx is not None:
        return str(outcome_idx)
    return "Unknown"


def fetch_trade_stats_for_market(condition_id, outcomes):
    stats = {
        outcome: {"trade_money": 0.0, "trade_trades": 0, "trade_wallets": set()}
        for outcome in outcomes
    }
    total_money = 0.0
    total_trades = 0
    total_wallets = set()
    truncated = False
    error = ""

    offset = 0
    while True:
        try:
            r = requests.get(
                TRADES_API,
                params={
                    "market": condition_id,
                    "limit": TRADES_PAGE_LIMIT,
                    "offset": offset,
                    "takerOnly": str(TRADES_TAKER_ONLY).lower(),
                },
                timeout=20,
            )
            r.raise_for_status()
            batch = r.json() or []
            if not isinstance(batch, list):
                break
        except Exception as exc:
            error = str(exc)
            break

        if not batch:
            break

        for trade in batch:
            outcome = _trade_outcome(trade, outcomes)
            entry = stats.setdefault(outcome, {"trade_money": 0.0, "trade_trades": 0, "trade_wallets": set()})
            size = _safe_float(trade.get("size"))
            price = _safe_float(trade.get("price"))
            if size is None or price is None:
                continue
            cash = size * price
            entry["trade_money"] += cash
            entry["trade_trades"] += 1
            total_money += cash
            total_trades += 1
            wallet = trade.get("proxyWallet")
            if wallet:
                entry["trade_wallets"].add(wallet)
                total_wallets.add(wallet)

        if len(batch) < TRADES_PAGE_LIMIT:
            break
        offset += TRADES_PAGE_LIMIT
        if offset > TRADES_MAX_OFFSET:
            truncated = True
            break

    return stats, total_money, total_trades, len(total_wallets), truncated, error


def build_holders_data(events, fetched_at):
    rows = []
    market_count = 0
    trade_rows = []

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
            outcomes_json = json.dumps(outcomes, ensure_ascii=True)
            prices_json = json.dumps(prices, ensure_ascii=True)

            trade_stats = None
            trade_total_money = 0.0
            trade_total_trades = 0
            trade_total_wallets = 0
            trade_truncated = False
            trade_error = ""
            if FETCH_TRADE_STATS:
                print(f"  Fetching trades for market {market_count}...")
                trade_stats, trade_total_money, trade_total_trades, trade_total_wallets, trade_truncated, trade_error = (
                    fetch_trade_stats_for_market(condition_id, outcomes)
                )

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
                        "market_outcomes": outcomes_json,
                        "market_prices": prices_json,
                        "holder": identity,
                        "wallet": wallet,
                        "outcome": outcome_name,
                        "outcomeIndex": outcome_idx,
                        "shares": shares,
                        "price": price,
                        "approxUsd": approx_usd,
                        "fetched_at": fetched_at,
                    })

            if trade_stats is not None:
                outcome_names = outcomes or list(trade_stats.keys())
                for outcome_name in outcome_names:
                    outcome_stats = trade_stats.get(outcome_name, {})
                    trade_rows.append({
                        "event_slug": event_slug,
                        "event_title": event_title,
                        "market_question": market_question,
                        "market_type": market_type,
                        "conditionId": condition_id,
                        "outcome": outcome_name,
                        "trade_money": float(outcome_stats.get("trade_money", 0.0)),
                        "trade_trades": int(outcome_stats.get("trade_trades", 0)),
                        "trade_unique_wallets": len(outcome_stats.get("trade_wallets", [])),
                        "trade_total_money": float(trade_total_money),
                        "trade_total_trades": int(trade_total_trades),
                        "trade_total_unique_wallets": int(trade_total_wallets),
                        "trade_truncated": bool(trade_truncated),
                        "trade_taker_only": bool(TRADES_TAKER_ONLY),
                        "trade_page_limit": int(TRADES_PAGE_LIMIT),
                        "trade_max_offset": int(TRADES_MAX_OFFSET),
                        "trade_error": trade_error,
                        "fetched_at": fetched_at,
                    })

            if MAX_MARKETS and market_count >= MAX_MARKETS:
                print(f"Reached market limit (UFC_MAX_MARKETS={MAX_MARKETS}). Stopping early.")
                break
        if MAX_MARKETS and market_count >= MAX_MARKETS:
            break

    print(f"\nProcessed {market_count} markets, found {len(rows)} holder positions")
    return rows, trade_rows


def save_to_csv(rows, timestamp):
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f"ufc_holders_{timestamp}.csv"
    filepath = os.path.join(DATA_DIR, filename)
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("approxUsd", ascending=False, na_position="last")
    df.to_csv(filepath, index=False)
    print(f"Saved {len(df)} rows to {filepath}")
    return filepath


def save_trade_stats_csv(rows, timestamp):
    if not rows:
        print("No trade stats rows to save.")
        return None
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f"ufc_trade_stats_{timestamp}.csv"
    filepath = os.path.join(DATA_DIR, filename)
    df = pd.DataFrame(rows)
    df.to_csv(filepath, index=False)
    print(f"Saved {len(df)} trade stat rows to {filepath}")
    return filepath


def main():
    print("UFC Whale Dashboard - Fetch Holders (scrape only)")
    print("=" * 60)
    events = fetch_ufc_fight_events()
    if not events:
        print("No active UFC events found")
        return
    fetched_at = datetime.now(timezone.utc).isoformat()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    rows, trade_rows = build_holders_data(events, fetched_at)
    if not rows:
        print("No holder data found")
        return
    save_to_csv(rows, timestamp)
    save_trade_stats_csv(trade_rows, timestamp)


if __name__ == "__main__":
    main()
