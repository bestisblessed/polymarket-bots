#!/usr/bin/env python3
"""
UFC Whale Dashboard - Sharp Betting Analytics

Fetches top holders for all UFC markets with:
1. Account P&L for each holder
2. Top 15 holders per side for each moneyline market
3. Money % vs Ticket % (public vs sharp indicator)

Docs:
- Gamma API: https://docs.polymarket.com/api-reference/core/get-market
- Holders API: https://docs.polymarket.com/api-reference/core/get-top-holders-for-markets
- Positions API: https://docs.polymarket.com/api-reference/core/get-positions
"""
import json
import os
import math
import time
from datetime import datetime, timezone

import pandas as pd
import requests
from tabulate import tabulate
from polymarket_apis import PolymarketDataClient

GAMMA_API = "https://gamma-api.polymarket.com/events"
DATA_API = "https://data-api.polymarket.com/holders"
POSITIONS_API = "https://data-api.polymarket.com/positions"
CLOSED_POSITIONS_API = "https://data-api.polymarket.com/closed-positions"

LIMIT_EVENTS = 200
LIMIT_HOLDERS = 50  # Fetch more to have enough for per-side tables
MIN_BALANCE = 10

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Cache for user P&L to avoid duplicate API calls
_pnl_cache = {}

# Shared data client for P&L lookups
_data_client = PolymarketDataClient()


def _parse_list(value):
    """Parse JSON string fields into lists."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return [value]
    return []


def get_user_pnl(wallet):
    """
    Fetch user's all-time P&L as shown on Polymarket profiles.

    Uses PolymarketDataClient.get_pnl(user=wallet), which returns a time series.
    The final point's value corresponds to the profile all-time P&L.
    """
    if wallet in _pnl_cache:
        return _pnl_cache[wallet]

    try:
        # First attempt
        series = _data_client.get_pnl(user=wallet)
        # If empty, backoff briefly and retry once
        if not series:
            time.sleep(0.2)
            series = _data_client.get_pnl(user=wallet)
        if not series:
            _pnl_cache[wallet] = None
            return None
        last_point = series[-1]
        pnl_value = getattr(last_point, "value", None)
        if pnl_value is None and isinstance(last_point, dict):
            pnl_value = last_point.get("value")
        _pnl_cache[wallet] = float(pnl_value) if pnl_value is not None else None
        return _pnl_cache[wallet]
    except Exception:
        _pnl_cache[wallet] = None
        return None


def format_pnl(pnl):
    """Format P&L with + or - prefix."""
    if pnl is None or (isinstance(pnl, (int, float)) and not math.isfinite(pnl)):
        return "N/A"
    if pnl >= 0:
        return f"+${pnl:,.0f}"
    else:
        return f"-${abs(pnl):,.0f}"


def fetch_ufc_fight_events():
    """Fetch all active UFC fight events that have moneyline markets."""
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
            has_moneyline = any(
                (m.get("sportsMarketType") or "") == "moneyline"
                for m in markets
            )
            if not has_moneyline:
                continue
            fight_events.append(ev)

        offset += len(events)

    print(f"Fetched {len(fight_events)} UFC fight events (with moneyline markets)")
    return fight_events


def fetch_holders_for_market(condition_id):
    """Fetch top holders for a market by conditionId."""
    try:
        r = requests.get(
            DATA_API,
            params={
                "market": condition_id,
                "limit": LIMIT_HOLDERS,
                "minBalance": MIN_BALANCE,
            },
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  Error fetching holders for {condition_id}: {e}")
        return []


def build_holders_data(events):
    """Build holders data for all markets in all events."""
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

                    identity = (
                        holder.get("name")
                        or holder.get("pseudonym")
                        or wallet
                    )

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


def fetch_pnl_for_holders(df):
    """Fetch P&L for all unique wallets in the dataframe sequentially (gentle on rate limits)."""
    unique_wallets = df['wallet'].unique()
    print(f"\nFetching P&L for {len(unique_wallets)} unique wallets...")

    pnl_data = {}
    for idx, wallet in enumerate(unique_wallets, start=1):
        pnl_data[wallet] = get_user_pnl(wallet)
        if idx % 10 == 0:
            print(f"  Fetched P&L for {idx}/{len(unique_wallets)} wallets...")
        # Small delay to avoid rate limits
        time.sleep(0.05)

    df['account_pnl'] = df['wallet'].map(pnl_data)
    return df


def save_to_csv(rows):
    """Save holder data to timestamped CSV file."""
    os.makedirs(DATA_DIR, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"ufc_holders_{timestamp}.csv"
    filepath = os.path.join(DATA_DIR, filename)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("approxUsd", ascending=False, na_position="last")

    df.to_csv(filepath, index=False)
    print(f"\nSaved {len(df)} rows to {filepath}")
    return filepath


def print_top_20_table(df):
    """Print top 20 holders with account P&L."""
    print("\n" + "=" * 90)
    print("TOP 20 HOLDERS ACROSS ALL UFC MARKETS")
    print("=" * 90)

    top = df.dropna(subset=["approxUsd"]).nlargest(20, "approxUsd").copy()

    table_data = []
    for i, (_, row) in enumerate(top.iterrows(), start=1):
        table_data.append([
            i,
            row['holder'][:18],
            f"${row['approxUsd']:,.0f}",
            row['outcome'][:12],
            row['event_slug'][:25],
            format_pnl(row.get('account_pnl'))
        ])

    print(tabulate(
        table_data,
        headers=["#", "Holder", "Position", "Outcome", "Fight", "Account P&L"],
        tablefmt="simple_outline"
    ))


def print_market_breakdown(df):
    """Print per-market breakdown with money % vs ticket %."""
    # Filter to moneyline markets only
    moneyline_df = df[df['market_type'] == 'moneyline'].copy()

    if moneyline_df.empty:
        print("\nNo moneyline markets found")
        return

    # Group by market (conditionId)
    markets = moneyline_df.groupby('conditionId').first()[['event_title', 'market_question', 'event_slug']].to_dict('index')

    for condition_id, market_info in markets.items():
        market_df = moneyline_df[moneyline_df['conditionId'] == condition_id].copy()

        # Get unique outcomes
        outcomes = market_df['outcome'].unique()
        if len(outcomes) < 2:
            continue

        # Clean up event title
        event_title = market_info['event_title']
        if '(' in event_title:
            event_title = event_title[:event_title.rfind('(')].strip()

        print("\n" + "=" * 90)
        print(event_title.upper())
        print("=" * 90)

        # Calculate money % and ticket % for each side
        total_usd = market_df['approxUsd'].sum()
        total_tickets = len(market_df)

        side_stats = {}
        for outcome in outcomes:
            side_df = market_df[market_df['outcome'] == outcome]
            side_usd = side_df['approxUsd'].sum()
            side_tickets = len(side_df)
            side_price = side_df['price'].iloc[0] if len(side_df) > 0 else 0

            money_pct = (side_usd / total_usd * 100) if total_usd > 0 else 0
            ticket_pct = (side_tickets / total_tickets * 100) if total_tickets > 0 else 0

            side_stats[outcome] = {
                'df': side_df,
                'money_pct': money_pct,
                'ticket_pct': ticket_pct,
                'price': side_price,
                'total_usd': side_usd
            }

        # Print side-by-side headers
        outcome_list = list(outcomes)[:2]  # Just first 2 outcomes

        for outcome in outcome_list:
            stats = side_stats[outcome]
            price_pct = stats['price'] * 100 if stats['price'] else 0
            print(f"\n{outcome.upper()} ({price_pct:.1f}%) - Money: {stats['money_pct']:.0f}% | Tickets: {stats['ticket_pct']:.0f}%")
            print("-" * 70)

            # Get top 15 for this side
            side_top = stats['df'].nlargest(15, 'approxUsd')

            table_data = []
            for i, (_, row) in enumerate(side_top.iterrows(), start=1):
                table_data.append([
                    i,
                    row['holder'][:20],
                    f"${row['approxUsd']:,.0f}",
                    format_pnl(row.get('account_pnl'))
                ])

            if table_data:
                print(tabulate(
                    table_data,
                    headers=["#", "Holder", "Position", "Account P&L"],
                    tablefmt="simple"
                ))
            else:
                print("  No holders found")


def print_prop_breakdown(df):
    """Print per-market breakdown for non-moneyline markets (props/totals/etc.)."""
    props_df = df[df['market_type'] != 'moneyline'].copy()

    if props_df.empty:
        print("\nNo non-moneyline (props/totals) markets found")
        return

    # Group by market (conditionId)
    markets = props_df.groupby('conditionId').first()[['event_title', 'market_question', 'event_slug']].to_dict('index')

    for condition_id, market_info in markets.items():
        market_df = props_df[props_df['conditionId'] == condition_id].copy()

        # Outcomes present
        outcomes = market_df['outcome'].unique()
        if len(outcomes) == 0:
            continue

        print("\n" + "=" * 90)
        print(market_info.get('event_title', '').upper())
        print(market_info.get('market_question', ''))
        print("=" * 90)

        total_usd = market_df['approxUsd'].sum()
        total_tickets = len(market_df)

        for outcome in outcomes:
            side_df = market_df[market_df['outcome'] == outcome]
            side_usd = side_df['approxUsd'].sum()
            side_tickets = len(side_df)
            money_pct = (side_usd / total_usd * 100) if total_usd > 0 else 0
            ticket_pct = (side_tickets / total_tickets * 100) if total_tickets > 0 else 0

            print(f"\n{outcome.upper()} - Money: {money_pct:.0f}% | Tickets: {ticket_pct:.0f}%")
            print("-" * 70)

            side_top = side_df.nlargest(15, 'approxUsd')
            table_data = []
            for i, (_, row) in enumerate(side_top.iterrows(), start=1):
                table_data.append([
                    i,
                    row['holder'][:20],
                    f"${row['approxUsd']:,.0f}" if pd.notna(row['approxUsd']) else "-",
                    format_pnl(row.get('account_pnl'))
                ])

            if table_data:
                print(tabulate(
                    table_data,
                    headers=["#", "Holder", "Position", "Account P&L"],
                    tablefmt="simple"
                ))
            else:
                print("  No holders found")


def main():
    print("UFC Whale Dashboard - Sharp Betting Analytics")
    print("=" * 50)
    print()

    events = fetch_ufc_fight_events()
    if not events:
        print("No active UFC events found")
        return

    rows = build_holders_data(events)
    if not rows:
        print("No holder data found")
        return

    # Create dataframe and fetch P&L
    df = pd.DataFrame(rows)
    df = fetch_pnl_for_holders(df)

    # Save to CSV
    save_to_csv(df.to_dict('records'))

    # Print tables
    print_top_20_table(df)
    print_market_breakdown(df)

    # Optional: print props/totals/other markets
    try:
        choice = input("\nPrint non-moneyline (props/totals) markets as well? [y/N]: ").strip().lower()
        if choice in ("y", "yes"):
            print_prop_breakdown(df)
    except EOFError:
        # Non-interactive environments: skip props
        pass

    print("\n" + "=" * 90)
    print("END OF REPORT")
    print("=" * 90)


if __name__ == "__main__":
    main()
