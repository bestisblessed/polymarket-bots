#!/usr/bin/env python3
"""
UFC Market Holders Fetcher

Fetches top 20 holders for all UFC markets (each fight and market type).
Saves data to JSON files for future analysis.

Usage:
    python fetch_ufc_market_holders.py [event_slug]
    python fetch_ufc_market_holders.py  # fetches all active UFC fights

APIs Used:
- Gamma API: https://gamma-api.polymarket.com/events (fetch UFC events)
- Data API: https://data-api.polymarket.com/holders (fetch top holders)

References:
- https://docs.polymarket.com/api-reference/events/list-events
- https://docs.polymarket.com/api-reference/core/get-top-holders-for-markets
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

# === API Endpoints ===
GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"

# === Output Settings ===
OUTPUT_DIR = "data"
TOP_HOLDERS_LIMIT = 20


def parse_json_field(value):
    """Parse a field that could be JSON string or already parsed."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return [value]
    return []


def fetch_ufc_events(*, limit: int = 200) -> list:
    """
    Fetch all active UFC events with moneyline markets.
    
    Ref: https://docs.polymarket.com/api-reference/events/list-events
    """
    offset = 0
    events = []

    print("[INFO] Fetching UFC events from Gamma API...")
    
    while True:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={
                "tag_slug": "ufc",
                "active": "true",
                "closed": "false",
                "archived": "false",
                "limit": limit,
                "offset": offset,
            },
            headers={"User-Agent": "curl/8.0"},
            timeout=60,
        )
        resp.raise_for_status()
        batch = resp.json() or []
        
        if not batch:
            break

        for ev in batch:
            markets = ev.get("markets") or []
            if not markets:
                continue
            # Only include events with moneyline markets
            has_moneyline = any(
                (m.get("sportsMarketType") or "") == "moneyline" 
                for m in markets
            )
            if not has_moneyline:
                continue
            events.append(ev)

        offset += len(batch)
        if len(batch) < limit:
            break

    print(f"[INFO] Found {len(events)} UFC events with moneyline markets")
    return events


def fetch_event_by_slug(slug: str) -> dict | None:
    """
    Fetch a single event by slug.
    
    Ref: https://docs.polymarket.com/api-reference/events/get-event-by-slug
    """
    print(f"[INFO] Fetching event: {slug}")
    
    resp = requests.get(
        f"{GAMMA_API}/events",
        params={"slug": slug},
        headers={"User-Agent": "curl/8.0"},
        timeout=30,
    )
    resp.raise_for_status()
    events = resp.json() or []
    
    if events:
        return events[0]
    return None


def fetch_holders_for_market(condition_id: str, *, limit: int = TOP_HOLDERS_LIMIT) -> list:
    """
    Fetch top holders for a market by condition ID.
    
    Ref: https://docs.polymarket.com/api-reference/core/get-top-holders-for-markets
    
    The /holders endpoint returns a list of token holder groups (one per outcome).
    Each group contains a 'holders' array with wallet, amount, outcomeIndex, etc.
    """
    resp = requests.get(
        f"{DATA_API}/holders",
        params={
            "market": condition_id,
            "limit": limit,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json() or []


def process_event_markets(event: dict) -> dict:
    """
    Process an event and fetch holders for all its markets.
    
    Returns a dict with event info and holders data for each market.
    """
    event_slug = event.get("slug", "")
    event_title = event.get("title", "")
    markets = event.get("markets") or []
    
    print(f"\n[EVENT] {event_title} ({event_slug})")
    print(f"  Markets: {len(markets)}")
    
    event_data = {
        "event_slug": event_slug,
        "event_title": event_title,
        "event_url": f"https://polymarket.com/event/{event_slug}",
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "markets": [],
    }
    
    for market in markets:
        condition_id = market.get("conditionId")
        market_slug = market.get("slug", "")
        question = market.get("question", "")
        market_type = market.get("sportsMarketType") or market.get("marketType") or "unknown"
        volume = market.get("volume") or market.get("volumeNum") or "0"
        
        outcomes = parse_json_field(market.get("outcomes") or [])
        prices_raw = parse_json_field(market.get("outcomePrices") or [])
        prices = []
        for p in prices_raw:
            try:
                prices.append(float(p))
            except (ValueError, TypeError):
                prices.append(None)
        
        if not condition_id:
            print(f"    [SKIP] No conditionId for: {question[:50]}")
            continue
        
        print(f"  [{market_type}] {question[:60]}...")
        
        # Fetch holders for this market
        try:
            holders_data = fetch_holders_for_market(condition_id, limit=TOP_HOLDERS_LIMIT)
        except Exception as e:
            print(f"    [ERROR] Failed to fetch holders: {e}")
            holders_data = []
        
        market_info = {
            "market_slug": market_slug,
            "question": question,
            "condition_id": condition_id,
            "market_type": market_type,
            "volume": volume,
            "outcomes": outcomes,
            "prices": prices,
            "holders_by_outcome": [],
        }
        
        # Process holders for each outcome/token
        for token_data in holders_data:
            holders = token_data.get("holders") or []
            if not holders:
                continue
            
            # Get outcome index from first holder
            outcome_idx = holders[0].get("outcomeIndex") if holders else None
            if isinstance(outcome_idx, int) and outcomes and outcome_idx < len(outcomes):
                outcome_name = outcomes[outcome_idx]
            else:
                outcome_name = str(outcome_idx) if outcome_idx is not None else "Unknown"
            
            # Get price for this outcome
            price = prices[outcome_idx] if isinstance(outcome_idx, int) and prices and outcome_idx < len(prices) else None
            
            outcome_holders = {
                "outcome_index": outcome_idx,
                "outcome_name": outcome_name,
                "price": price,
                "holders": [],
            }
            
            for h in holders[:TOP_HOLDERS_LIMIT]:
                wallet = h.get("proxyWallet", "")
                amount = float(h.get("amount", 0))
                name = h.get("name") or h.get("pseudonym") or wallet
                
                # Calculate approximate USD value
                approx_usd = amount * price if price is not None else None
                
                outcome_holders["holders"].append({
                    "name": name,
                    "wallet": wallet,
                    "shares": amount,
                    "approx_usd": approx_usd,
                })
            
            holder_count = len(outcome_holders["holders"])
            print(f"    {outcome_name}: {holder_count} holders")
            market_info["holders_by_outcome"].append(outcome_holders)
        
        event_data["markets"].append(market_info)
        
        # Small delay to avoid rate limiting
        time.sleep(0.2)
    
    return event_data


def save_event_data(event_data: dict, output_dir: str) -> str:
    """Save event data to a JSON file."""
    os.makedirs(output_dir, exist_ok=True)
    
    event_slug = event_data.get("event_slug", "unknown")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"{event_slug}_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, "w") as f:
        json.dump(event_data, f, indent=2)
    
    return filepath


def save_summary(all_events_data: list, output_dir: str) -> str:
    """Save a summary file with all events."""
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"ufc_holders_summary_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total_events": len(all_events_data),
        "total_markets": sum(len(e.get("markets", [])) for e in all_events_data),
        "events": all_events_data,
    }
    
    with open(filepath, "w") as f:
        json.dump(summary, f, indent=2)
    
    return filepath


def main():
    print("=" * 60)
    print("UFC Market Holders Fetcher")
    print("=" * 60)
    print()
    print("APIs Used:")
    print("- Gamma API: https://gamma-api.polymarket.com/events")
    print("- Data API: https://data-api.polymarket.com/holders")
    print()
    
    # Check for specific event slug argument
    if len(sys.argv) > 1:
        slug = sys.argv[1]
        event = fetch_event_by_slug(slug)
        if not event:
            print(f"[ERROR] Event not found: {slug}")
            sys.exit(1)
        events = [event]
    else:
        # Fetch all active UFC events
        events = fetch_ufc_events()
    
    if not events:
        print("[ERROR] No UFC events found")
        sys.exit(1)
    
    print(f"\n[INFO] Processing {len(events)} events...")
    
    all_events_data = []
    
    for event in events:
        try:
            event_data = process_event_markets(event)
            all_events_data.append(event_data)
            
            # Save individual event file
            filepath = save_event_data(event_data, OUTPUT_DIR)
            print(f"  Saved: {filepath}")
            
        except Exception as e:
            event_slug = event.get("slug", "unknown")
            print(f"[ERROR] Failed to process {event_slug}: {e}")
            continue
        
        # Delay between events
        time.sleep(0.5)
    
    # Save summary file
    summary_path = save_summary(all_events_data, OUTPUT_DIR)
    
    print()
    print("=" * 60)
    print(f"[DONE] Processed {len(all_events_data)} events")
    print(f"[DONE] Summary saved: {summary_path}")
    print(f"[DONE] Individual files in: {OUTPUT_DIR}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
