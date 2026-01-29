#!/usr/bin/env python3
"""
Compute Account P&L and UFC-only P&L for a holders CSV, then print tables.

Usage:
  python report_ufc_holders.py [path_to_csv]

If no path is provided, the latest data/ufc_holders_*.csv is used.
Outputs tables to stdout and saves a new CSV with updated P&L columns.
If a matching ufc_trade_stats_*.csv exists, the report prints all-trades
breakdowns alongside whales-only holder snapshots.
"""

import glob
import json
import os
import re
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


def trade_stats_path_for_holders(holders_path: str):
    if not holders_path:
        return None
    dirname = os.path.dirname(holders_path)
    base = os.path.basename(holders_path)
    match = re.match(r"ufc_holders_(\d{8}_\d{6})\.csv$", base)
    if match:
        candidate = os.path.join(dirname, f"ufc_trade_stats_{match.group(1)}.csv")
        if os.path.isfile(candidate):
            return candidate
    # fallback: latest trade stats in same directory
    pattern = os.path.join(dirname, "ufc_trade_stats_*.csv")
    files = sorted(glob.glob(pattern), reverse=True)
    return files[0] if files else None


def format_pnl(pnl):
    if pnl is None or not isinstance(pnl, (int, float)):
        return "N/A"
    if pnl >= 0:
        return f"+${pnl:,.0f}"
    return f"-${abs(pnl):,.0f}"


def _parse_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return [value]
    return []


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "y")
    return False


def _extract_market_outcomes(mdf: pd.DataFrame) -> list[str]:
    if "market_outcomes" in mdf.columns:
        raw = mdf["market_outcomes"].dropna()
        if not raw.empty:
            parsed = _parse_list(raw.iloc[0])
            if parsed:
                return parsed
    outcomes = [str(o) for o in mdf["outcome"].dropna().unique().tolist()]
    return outcomes


def _extract_market_prices(mdf: pd.DataFrame) -> list[float]:
    if "market_prices" in mdf.columns:
        raw = mdf["market_prices"].dropna()
        if not raw.empty:
            parsed = _parse_list(raw.iloc[0])
            if parsed:
                return parsed
    return []


def _outcome_price_map(outcomes: list[str], prices: list[float]) -> dict[str, float]:
    mapping = {}
    for idx, outcome in enumerate(outcomes):
        if idx < len(prices) and prices[idx] is not None:
            try:
                mapping[outcome] = float(prices[idx])
            except (TypeError, ValueError):
                continue
    return mapping


def load_trade_stats(path):
    if not path or not os.path.isfile(path):
        return {}, {}
    df = pd.read_csv(path)
    stats = {}
    meta = {}
    for _, row in df.iterrows():
        condition_id = row.get("conditionId")
        outcome = row.get("outcome")
        if pd.isna(condition_id) or pd.isna(outcome):
            continue
        stats.setdefault(condition_id, {})[outcome] = row
        if condition_id not in meta:
            meta[condition_id] = {
                "trade_total_money": row.get("trade_total_money", 0),
                "trade_total_trades": row.get("trade_total_trades", 0),
                "trade_total_unique_wallets": row.get("trade_total_unique_wallets", 0),
                "trade_truncated": row.get("trade_truncated", False),
                "trade_taker_only": row.get("trade_taker_only", True),
                "trade_error": row.get("trade_error", ""),
            }
    return stats, meta


def _compute_holder_stats(mdf: pd.DataFrame, outcomes: list[str]) -> tuple[dict, float, int]:
    total_money = mdf["approxUsd"].sum()
    total_tickets = len(mdf)
    stats = {}
    for outcome in outcomes:
        side = mdf[mdf["outcome"] == outcome]
        side_money = side["approxUsd"].sum()
        side_tickets = len(side)
        stats[outcome] = {
            "df": side,
            "money": side_money,
            "tickets": side_tickets,
            "money_pct": (side_money / total_money * 100) if total_money > 0 else 0,
            "ticket_pct": (side_tickets / total_tickets * 100) if total_tickets > 0 else 0,
        }
    return stats, total_money, total_tickets


def _compute_trade_stats(condition_id: str, outcomes: list[str], trade_stats: dict, trade_meta: dict) -> tuple[dict, dict]:
    market_stats = {}
    total_money = 0.0
    total_trades = 0
    total_wallets = 0
    meta = trade_meta.get(condition_id, {}) if trade_meta else {}

    for outcome in outcomes:
        row = trade_stats.get(condition_id, {}).get(outcome) if trade_stats else None
        money = float(row.get("trade_money", 0.0)) if row is not None else 0.0
        trades = int(row.get("trade_trades", 0)) if row is not None else 0
        wallets = int(row.get("trade_unique_wallets", 0)) if row is not None else 0
        market_stats[outcome] = {
            "money": money,
            "trades": trades,
            "wallets": wallets,
        }

    if meta:
        try:
            total_money = float(meta.get("trade_total_money", 0.0))
        except (TypeError, ValueError):
            total_money = 0.0
        try:
            total_trades = int(meta.get("trade_total_trades", 0))
        except (TypeError, ValueError):
            total_trades = 0
        try:
            total_wallets = int(meta.get("trade_total_unique_wallets", 0))
        except (TypeError, ValueError):
            total_wallets = 0
    else:
        total_money = sum(v["money"] for v in market_stats.values())
        total_trades = sum(v["trades"] for v in market_stats.values())
        total_wallets = sum(v["wallets"] for v in market_stats.values())

    meta_out = {
        "trade_total_money": total_money,
        "trade_total_trades": total_trades,
        "trade_total_unique_wallets": total_wallets,
        "trade_truncated": _as_bool(meta.get("trade_truncated", False)),
        "trade_taker_only": _as_bool(meta.get("trade_taker_only", True)),
        "trade_error": meta.get("trade_error", "") if meta else "",
    }
    return market_stats, meta_out


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
        time.sleep(0.05)
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


def print_moneyline(df, trade_stats=None, trade_meta=None):
    moneyline_df = df[df['market_type'] == 'moneyline'].copy()
    if moneyline_df.empty:
        print("\nNo moneyline markets found")
        return
    markets = moneyline_df.groupby('conditionId').first()[['event_title', 'market_question', 'event_slug']].to_dict('index')
    for condition_id, info in markets.items():
        mdf = moneyline_df[moneyline_df['conditionId'] == condition_id].copy()
        outcomes = _extract_market_outcomes(mdf)
        if len(outcomes) < 2:
            continue
        prices = _extract_market_prices(mdf)
        price_map = _outcome_price_map(outcomes, prices)
        event_title = info['event_title']
        if '(' in event_title:
            event_title = event_title[:event_title.rfind('(')].strip()
        print("\n" + "=" * 90)
        print(event_title.upper())
        print("=" * 90)

        holder_stats, holder_total_money, holder_total_tickets = _compute_holder_stats(mdf, outcomes)
        has_trade_stats = bool(trade_stats) and condition_id in trade_stats
        trade_stats_by_outcome = {}
        trade_meta_info = {}
        if has_trade_stats:
            trade_stats_by_outcome, trade_meta_info = _compute_trade_stats(condition_id, outcomes, trade_stats, trade_meta)
            print("ALL-TRADES (taker-only): Money=$ sum(size*price) | Tickets=trade count")
            if trade_meta_info.get("trade_truncated"):
                print("  Note: Trade history truncated at API offset limit.")
            if trade_meta_info.get("trade_error"):
                print(f"  Note: Trade fetch error: {trade_meta_info.get('trade_error')}")
        else:
            print("ALL-TRADES: unavailable (no trade stats file found).")
        print("WHALES-ONLY (top holders snapshot): Money=$ sum(shares*price) | Tickets=holder count")

        for outcome in outcomes:
            holder_side = holder_stats.get(outcome, {})
            price = price_map.get(outcome)
            if price is None:
                side_df = holder_side.get("df")
                if side_df is not None and not side_df.empty:
                    price = side_df["price"].iloc[0]
            price_pct = price * 100 if price else 0

            print(f"\n{outcome.upper()} ({price_pct:.1f}%)")
            if has_trade_stats:
                trade_entry = trade_stats_by_outcome.get(outcome, {})
                trade_money = trade_entry.get("money", 0.0)
                trade_trades = trade_entry.get("trades", 0)
                trade_wallets = trade_entry.get("wallets", 0)
                trade_money_pct = (
                    trade_money / trade_meta_info.get("trade_total_money", 0) * 100
                    if trade_meta_info.get("trade_total_money", 0) > 0 else 0
                )
                trade_ticket_pct = (
                    trade_trades / trade_meta_info.get("trade_total_trades", 0) * 100
                    if trade_meta_info.get("trade_total_trades", 0) > 0 else 0
                )
                print(
                    f"  All-trades: Money ${trade_money:,.0f} ({trade_money_pct:.1f}%) | "
                    f"Tickets {trade_trades} ({trade_ticket_pct:.1f}%) | "
                    f"Unique wallets {trade_wallets}"
                )
            holder_money = holder_side.get("money", 0.0)
            holder_tickets = holder_side.get("tickets", 0)
            holder_money_pct = holder_side.get("money_pct", 0.0)
            holder_ticket_pct = holder_side.get("ticket_pct", 0.0)
            print(
                f"  Whales-only: Money ${holder_money:,.0f} ({holder_money_pct:.1f}%) | "
                f"Tickets {holder_tickets} ({holder_ticket_pct:.1f}%)"
            )
            print("-" * 70)
            side_df = holder_side.get("df")
            if side_df is None:
                side_df = mdf[mdf["outcome"] == outcome]
            side_top = side_df.nlargest(15, "approxUsd")
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


def print_props(df, trade_stats=None, trade_meta=None):
    props_df = df[df['market_type'] != 'moneyline'].copy()
    if props_df.empty:
        print("\nNo non-moneyline (props/totals) markets found")
        return
    markets = props_df.groupby('conditionId').first()[['event_title', 'market_question', 'event_slug']].to_dict('index')
    for condition_id, info in markets.items():
        mdf = props_df[props_df['conditionId'] == condition_id].copy()
        outcomes = _extract_market_outcomes(mdf)
        if len(outcomes) == 0:
            continue
        print("\n" + "=" * 90)
        print(info.get('event_title', '').upper())
        print(info.get('market_question', ''))
        print("=" * 90)
        holder_stats, holder_total_money, holder_total_tickets = _compute_holder_stats(mdf, outcomes)
        has_trade_stats = bool(trade_stats) and condition_id in trade_stats
        trade_stats_by_outcome = {}
        trade_meta_info = {}
        if has_trade_stats:
            trade_stats_by_outcome, trade_meta_info = _compute_trade_stats(condition_id, outcomes, trade_stats, trade_meta)
            print("ALL-TRADES (taker-only): Money=$ sum(size*price) | Tickets=trade count")
            if trade_meta_info.get("trade_truncated"):
                print("  Note: Trade history truncated at API offset limit.")
            if trade_meta_info.get("trade_error"):
                print(f"  Note: Trade fetch error: {trade_meta_info.get('trade_error')}")
        else:
            print("ALL-TRADES: unavailable (no trade stats file found).")
        print("WHALES-ONLY (top holders snapshot): Money=$ sum(shares*price) | Tickets=holder count")
        for outcome in outcomes:
            holder_side = holder_stats.get(outcome, {})
            print(f"\n{outcome.upper()}")
            if has_trade_stats:
                trade_entry = trade_stats_by_outcome.get(outcome, {})
                trade_money = trade_entry.get("money", 0.0)
                trade_trades = trade_entry.get("trades", 0)
                trade_wallets = trade_entry.get("wallets", 0)
                trade_money_pct = (
                    trade_money / trade_meta_info.get("trade_total_money", 0) * 100
                    if trade_meta_info.get("trade_total_money", 0) > 0 else 0
                )
                trade_ticket_pct = (
                    trade_trades / trade_meta_info.get("trade_total_trades", 0) * 100
                    if trade_meta_info.get("trade_total_trades", 0) > 0 else 0
                )
                print(
                    f"  All-trades: Money ${trade_money:,.0f} ({trade_money_pct:.1f}%) | "
                    f"Tickets {trade_trades} ({trade_ticket_pct:.1f}%) | "
                    f"Unique wallets {trade_wallets}"
                )
            holder_money = holder_side.get("money", 0.0)
            holder_tickets = holder_side.get("tickets", 0)
            holder_money_pct = holder_side.get("money_pct", 0.0)
            holder_ticket_pct = holder_side.get("ticket_pct", 0.0)
            print(
                f"  Whales-only: Money ${holder_money:,.0f} ({holder_money_pct:.1f}%) | "
                f"Tickets {holder_tickets} ({holder_ticket_pct:.1f}%)"
            )
            print("-" * 70)
            side_df = holder_side.get("df")
            if side_df is None:
                side_df = mdf[mdf["outcome"] == outcome]
            side_top = side_df.nlargest(15, "approxUsd")
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

    trade_stats_path = trade_stats_path_for_holders(path)
    if trade_stats_path:
        print(f"Loading trade stats from {trade_stats_path}...")
    else:
        print("No trade stats file found. All-trades sections will be unavailable.")
    trade_stats, trade_meta = load_trade_stats(trade_stats_path)

    print(f"Computing P&L for {df['wallet'].nunique()} wallets...")
    df = compute_pnls(df)

    save_csv(df, path)

    print_top_20(df)
    print_top_20_by_pnl(df, "ufc_pnl", "TOP 20 BY UFC P&L (WALLETS)")
    print_top_20_by_pnl(df, "account_pnl", "TOP 20 BY ACCOUNT P&L (WALLETS)")
    print_moneyline(df, trade_stats, trade_meta)

    try:
        choice = input("\nPrint non-moneyline (props/totals) markets as well? [y/N]: ").strip().lower()
        if choice in ("y", "yes"):
            print_props(df, trade_stats, trade_meta)
    except EOFError:
        pass

    print("\n" + "=" * 90)
    print("END OF REPORT")
    print("=" * 90)


if __name__ == "__main__":
    main()
