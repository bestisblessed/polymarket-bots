#!/usr/bin/env python3
"""
Compute Account P&L and UFC-only P&L for a holders CSV, then print tables.

Usage:
  python report_ufc_holders.py [path_to_csv]

If no path is provided, the latest data/ufc_holders_*.csv is used.
Outputs tables to stdout and saves a new CSV with updated P&L columns.
"""

import glob
import json
import os
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import requests
from polymarket_apis import PolymarketDataClient
from tabulate import tabulate

POSITIONS_API = "https://data-api.polymarket.com/positions"
CLOSED_POSITIONS_API = "https://data-api.polymarket.com/closed-positions"

_pnl_cache = {}
_ufc_pnl_cache = {}
_client = PolymarketDataClient()


def latest_csv():
    files = sorted(glob.glob("data/ufc_holders_*.csv"), reverse=True)
    return files[0] if files else None


def format_pnl(pnl):
    if pnl is None or not isinstance(pnl, (int, float)):
        return "N/A"
    if pnl >= 0:
        return f"+${pnl:,.0f}"
    return f"-${abs(pnl):,.0f}"


def get_user_pnl(wallet):
    if wallet in _pnl_cache:
        return _pnl_cache[wallet]
    try:
        series = _client.get_pnl(user=wallet)
        if not series:
            time.sleep(0.2)
            series = _client.get_pnl(user=wallet)
        if not series:
            _pnl_cache[wallet] = None
            return None
        last_point = series[-1]
        val = getattr(last_point, "value", None)
        if val is None and isinstance(last_point, dict):
            val = last_point.get("value")
        _pnl_cache[wallet] = float(val) if val is not None else None
        return _pnl_cache[wallet]
    except Exception:
        _pnl_cache[wallet] = None
        return None


def _is_ufc(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    for f in (entry.get("eventSlug"), entry.get("slug"), entry.get("title"), entry.get("eventTitle")):
        if isinstance(f, str) and "ufc" in f.lower():
            return True
    return False


def _sum_closed_ufc(wallet):
    total = 0.0
    offset = 0
    limit = 500
    while True:
        try:
            resp = requests.get(CLOSED_POSITIONS_API, params={"user": wallet, "limit": limit, "offset": offset}, timeout=15)
            if not resp.ok or not resp.text.strip():
                break
            try:
                data = resp.json()
                if not isinstance(data, list):
                    break
            except json.JSONDecodeError:
                data = []
                for line in resp.text.strip().splitlines():
                    try:
                        data.append(json.loads(line))
                    except Exception:
                        continue
            if not data:
                break
            for pos in data:
                if _is_ufc(pos):
                    pnl_val = pos.get("pnl")
                    if pnl_val is None:
                        pnl_val = pos.get("realizedPnl", 0)
                    try:
                        total += float(pnl_val or 0)
                    except Exception:
                        pass
            if len(data) < limit:
                break
            offset += limit
        except Exception:
            break
    return total


def _sum_open_ufc(wallet):
    try:
        resp = requests.get(POSITIONS_API, params={"user": wallet}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return 0.0
    except Exception:
        return 0.0
    total = 0.0
    for pos in data:
        if not _is_ufc(pos):
            continue
        cash = pos.get("cashPnl", 0)
        realized = pos.get("realizedPnl", 0)
        try:
            total += float(cash or 0) + float(realized or 0)
        except Exception:
            pass
    return total


def get_user_ufc_pnl(wallet):
    if wallet in _ufc_pnl_cache:
        return _ufc_pnl_cache[wallet]
    try:
        total = _sum_open_ufc(wallet) + _sum_closed_ufc(wallet)
        _ufc_pnl_cache[wallet] = total
        return total
    except Exception:
        _ufc_pnl_cache[wallet] = None
        return None


def compute_pnls(df: pd.DataFrame) -> pd.DataFrame:
    wallets = df['wallet'].dropna().unique()
    pnl_map = {}
    ufc_pnl_map = {}
    for idx, w in enumerate(wallets, start=1):
        pnl_map[w] = get_user_pnl(w)
        ufc_pnl_map[w] = get_user_ufc_pnl(w)
        if idx % 10 == 0:
            print(f"  Fetched P&L for {idx}/{len(wallets)} wallets...")
        time.sleep(0.025)
    df['account_pnl'] = df['wallet'].map(pnl_map)
    df['ufc_pnl'] = df['wallet'].map(ufc_pnl_map)
    return df


def save_csv(df: pd.DataFrame, source_path: str) -> str:
    base, ext = os.path.splitext(source_path)
    out = f"{base}_pnl{ext}"
    df.to_csv(out, index=False)
    print(f"Saved updated CSV to {out}")
    return out


def print_top_20(df):
    print("\n" + "=" * 90)
    print("TOP 20 HOLDERS ACROSS ALL UFC MARKETS")
    print("=" * 90)
    top = df.dropna(subset=["approxUsd"]).nlargest(20, "approxUsd").copy()
    table = []
    for i, (_, row) in enumerate(top.iterrows(), start=1):
        table.append([
            i,
            row['holder'][:18],
            f"${row['approxUsd']:,.0f}",
            row['outcome'][:12],
            row['event_slug'][:25],
            format_pnl(row.get('account_pnl')),
            format_pnl(row.get('ufc_pnl')),
        ])
    print(tabulate(table, headers=["#", "Holder", "Position", "Outcome", "Fight", "Account P&L", "UFC P&L"], tablefmt="simple_outline"))


def print_top_20_by_pnl(df: pd.DataFrame, col: str, title: str):
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)

    top = df.dropna(subset=[col]).nlargest(20, col).copy()
    table = []
    for i, (_, row) in enumerate(top.iterrows(), start=1):
        table.append([
            i,
            row['holder'][:22],
            format_pnl(row.get('account_pnl')),
            format_pnl(row.get('ufc_pnl')),
        ])

    print(tabulate(table, headers=["#", "Holder", "Account P&L", "UFC P&L"], tablefmt="simple_outline"))


def print_moneyline(df):
    moneyline_df = df[df['market_type'] == 'moneyline'].copy()
    if moneyline_df.empty:
        print("\nNo moneyline markets found")
        return
    markets = moneyline_df.groupby('conditionId').first()[['event_title', 'market_question', 'event_slug']].to_dict('index')
    for condition_id, info in markets.items():
        mdf = moneyline_df[moneyline_df['conditionId'] == condition_id].copy()
        outcomes = mdf['outcome'].unique()
        if len(outcomes) < 2:
            continue
        event_title = info['event_title']
        if '(' in event_title:
            event_title = event_title[:event_title.rfind('(')].strip()
        print("\n" + "=" * 90)
        print(event_title.upper())
        print("=" * 90)
        total_usd = mdf['approxUsd'].sum()
        total_tickets = len(mdf)
        stats = {}
        for outcome in outcomes:
            side = mdf[mdf['outcome'] == outcome]
            side_usd = side['approxUsd'].sum()
            side_tickets = len(side)
            price = side['price'].iloc[0] if len(side) > 0 else 0
            stats[outcome] = {
                'df': side,
                'money_pct': (side_usd / total_usd * 100) if total_usd > 0 else 0,
                'ticket_pct': (side_tickets / total_tickets * 100) if total_tickets > 0 else 0,
                'price': price,
            }
        for outcome in list(outcomes)[:2]:
            s = stats[outcome]
            price_pct = s['price'] * 100 if s['price'] else 0
            print(f"\n{outcome.upper()} ({price_pct:.1f}%) - Money: {s['money_pct']:.0f}% | Tickets: {s['ticket_pct']:.0f}%")
            print("-" * 70)
            side_top = s['df'].nlargest(15, 'approxUsd')
            table = []
            for i, (_, row) in enumerate(side_top.iterrows(), start=1):
                table.append([
                    i,
                    row['holder'][:20],
                    f"${row['approxUsd']:,.0f}",
                    format_pnl(row.get('account_pnl')),
                    format_pnl(row.get('ufc_pnl')),
                ])
            if table:
                print(tabulate(table, headers=["#", "Holder", "Position", "Account P&L", "UFC P&L"], tablefmt="simple"))
            else:
                print("  No holders found")


def print_props(df):
    props_df = df[df['market_type'] != 'moneyline'].copy()
    if props_df.empty:
        print("\nNo non-moneyline (props/totals) markets found")
        return
    markets = props_df.groupby('conditionId').first()[['event_title', 'market_question', 'event_slug']].to_dict('index')
    for condition_id, info in markets.items():
        mdf = props_df[props_df['conditionId'] == condition_id].copy()
        outcomes = mdf['outcome'].unique()
        if len(outcomes) == 0:
            continue
        print("\n" + "=" * 90)
        print(info.get('event_title', '').upper())
        print(info.get('market_question', ''))
        print("=" * 90)
        total_usd = mdf['approxUsd'].sum()
        total_tickets = len(mdf)
        for outcome in outcomes:
            side = mdf[mdf['outcome'] == outcome]
            side_usd = side['approxUsd'].sum()
            side_tickets = len(side)
            money_pct = (side_usd / total_usd * 100) if total_usd > 0 else 0
            ticket_pct = (side_tickets / total_tickets * 100) if total_tickets > 0 else 0
            print(f"\n{outcome.upper()} - Money: {money_pct:.0f}% | Tickets: {ticket_pct:.0f}%")
            print("-" * 70)
            side_top = side.nlargest(15, 'approxUsd')
            table = []
            for i, (_, row) in enumerate(side_top.iterrows(), start=1):
                table.append([
                    i,
                    row['holder'][:20],
                    f"${row['approxUsd']:,.0f}" if pd.notna(row['approxUsd']) else "-",
                    format_pnl(row.get('account_pnl')),
                    format_pnl(row.get('ufc_pnl')),
                ])
            if table:
                print(tabulate(table, headers=["#", "Holder", "Position", "Account P&L", "UFC P&L"], tablefmt="simple"))
            else:
                print("  No holders found")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else latest_csv()
    if not path or not os.path.isfile(path):
        print("No input CSV found. Pass a path or ensure data/ has ufc_holders_*.csv")
        sys.exit(1)

    print("UFC Whale Dashboard - Report (P&L + Tables)")
    print("=" * 60)
    print(f"Loading {path}...")
    df = pd.read_csv(path)
    if df.empty:
        print("Input CSV is empty")
        sys.exit(1)

    print(f"Computing P&L for {df['wallet'].nunique()} wallets...")
    df = compute_pnls(df)

    save_csv(df, path)

    print_top_20(df)
    print_top_20_by_pnl(df, "ufc_pnl", "TOP 20 BY UFC P&L (WALLETS)")
    print_top_20_by_pnl(df, "account_pnl", "TOP 20 BY ACCOUNT P&L (WALLETS)")
    print_moneyline(df)
    print_props(df)

    print("\n" + "=" * 90)
    print("END OF REPORT")
    print("=" * 90)


if __name__ == "__main__":
    main()
