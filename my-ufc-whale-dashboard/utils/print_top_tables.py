#!/usr/bin/env python3
"""
Print Top 20 tables from an existing holders CSV (with P&L columns).

Usage:
  python print_top_tables.py [path_to_csv]

- If no path is provided, the script picks the latest *_pnl.csv if present,
  otherwise the latest ufc_holders_*.csv.
- Expects columns: holder, approxUsd, outcome, event_slug, account_pnl, ufc_pnl.
"""

import glob
import os
import sys

import pandas as pd
from tabulate import tabulate


def latest_csv():
    files = sorted(glob.glob("data/ufc_holders_*_pnl.csv"), reverse=True)
    if files:
        return files[0]
    files = sorted(glob.glob("data/ufc_holders_*.csv"), reverse=True)
    return files[0] if files else None


def format_pnl(v):
    if v is None or not isinstance(v, (int, float)):
        return "N/A"
    return f"+${v:,.0f}" if v >= 0 else f"-${abs(v):,.0f}"


def top_by_position(df):
    top = df.dropna(subset=["approxUsd"]).nlargest(20, "approxUsd")
    table = []
    for i, (_, r) in enumerate(top.iterrows(), start=1):
        table.append([
            i,
            r.get("holder", "")[:18],
            f"${r['approxUsd']:,.0f}",
            str(r.get("outcome", ""))[:12],
            str(r.get("event_slug", ""))[:25],
            format_pnl(r.get("account_pnl")),
            format_pnl(r.get("ufc_pnl")),
        ])
    return table


def top_by_column(df, col):
    top = df.dropna(subset=[col]).nlargest(20, col)
    table = []
    for i, (_, r) in enumerate(top.iterrows(), start=1):
        table.append([
            i,
            r.get("holder", "")[:22],
            format_pnl(r.get("account_pnl")),
            format_pnl(r.get("ufc_pnl")),
        ])
    return table


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else latest_csv()
    if not path or not os.path.isfile(path):
        print("No input CSV found. Provide a path or ensure data/ has a holders CSV.")
        sys.exit(1)

    df = pd.read_csv(path)
    for col in ["holder", "approxUsd", "outcome", "event_slug", "account_pnl", "ufc_pnl"]:
        if col not in df.columns:
            print(f"Missing column '{col}' in {path}. Ensure you ran report_ufc_holders.py first.")
            sys.exit(1)

    print("Using", path)

    print("\n" + "=" * 90)
    print("TOP 20 HOLDERS ACROSS ALL UFC MARKETS")
    print("=" * 90)
    print(tabulate(top_by_position(df), headers=["#", "Holder", "Position", "Outcome", "Fight", "Account P&L", "UFC P&L"], tablefmt="simple_outline"))

    print("\n" + "=" * 90)
    print("TOP 20 BY UFC P&L (WALLETS)")
    print("=" * 90)
    print(tabulate(top_by_column(df, "ufc_pnl"), headers=["#", "Holder", "Account P&L", "UFC P&L"], tablefmt="simple_outline"))

    print("\n" + "=" * 90)
    print("TOP 20 BY ACCOUNT P&L (WALLETS)")
    print("=" * 90)
    print(tabulate(top_by_column(df, "account_pnl"), headers=["#", "Holder", "Account P&L", "UFC P&L"], tablefmt="simple_outline"))


if __name__ == "__main__":
    main()
