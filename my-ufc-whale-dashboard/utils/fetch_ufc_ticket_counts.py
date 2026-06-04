#!/usr/bin/env python3
"""
Fetch ticket counts (BUY trades) per outcome for active UFC markets.

Outputs data/all_ufc_ticket_counts.json as a list of:
  {
    "conditionId": "0x...",
    "totalTickets": 123,
    "outcomes": {"Yes": 45, "No": 78}
  }
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import requests

GAMMA_API = "https://gamma-api.polymarket.com/events"
TRADES_API = "https://data-api.polymarket.com/trades"

LIMIT_EVENTS = 200
LIMIT_TRADES = 10000
EVENT_BATCH_SIZE = 10
SLEEP_BETWEEN_PAGES = 0.1

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "all_ufc_ticket_counts.json")


def fetch_ufc_fight_events() -> list[dict]:
    offset = 0
    fight_events: list[dict] = []
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


def _chunks(items: list[str], size: int):
    for idx in range(0, len(items), size):
        yield items[idx:idx + size]


def fetch_trades_for_events(event_ids: list[str]) -> list[dict]:
    if not event_ids:
        return []

    all_trades: list[dict] = []
    offset = 0
    while True:
        r = requests.get(
            TRADES_API,
            params={
                "eventId": ",".join(event_ids),
                "limit": LIMIT_TRADES,
                "offset": offset,
                "side": "BUY",
            },
            timeout=60,
        )
        r.raise_for_status()
        trades = r.json() or []
        if not trades:
            break
        all_trades.extend(trades)
        if len(trades) < LIMIT_TRADES:
            break
        offset += LIMIT_TRADES
        time.sleep(SLEEP_BETWEEN_PAGES)
    return all_trades


def fetch_trades_for_event(event_id: str) -> list[dict]:
    return fetch_trades_for_events([event_id])


def build_ticket_counts(
    events: list[dict],
    batch_size: int = EVENT_BATCH_SIZE,
    fetcher=fetch_trades_for_events,
) -> dict[str, dict]:
    ticket_counts: dict[str, dict] = {}
    event_ids = [str(event.get("id")) for event in events if event.get("id")]

    for batch in _chunks(event_ids, batch_size):
        print(f"Fetching trades for {len(batch)} events...")
        try:
            trades = fetcher(batch)
        except Exception as exc:
            print(f"  Error fetching trades for events {','.join(batch)}: {exc}")
            continue

        for trade in trades:
            condition_id = trade.get("conditionId")
            outcome = trade.get("outcome")
            if not condition_id or not outcome:
                continue
            condition_id = str(condition_id)
            entry = ticket_counts.setdefault(condition_id, {"totalTickets": 0, "outcomes": {}})
            entry["totalTickets"] += 1
            entry["outcomes"][outcome] = entry["outcomes"].get(outcome, 0) + 1

    return ticket_counts


def save_ticket_counts(ticket_counts: dict[str, dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    output = []
    for condition_id, data in ticket_counts.items():
        output.append({
            "conditionId": condition_id,
            "totalTickets": data.get("totalTickets", 0),
            "outcomes": data.get("outcomes", {}),
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
        })
    with open(OUTPUT_FILE, "w") as file:
        json.dump(output, file)
    print(f"Saved ticket counts to {OUTPUT_FILE}")


def main() -> None:
    print("UFC Whale Dashboard - Fetch Ticket Counts (BUY trades)")
    print("=" * 60)
    events = fetch_ufc_fight_events()
    if not events:
        print("No active UFC events found")
        return
    ticket_counts = build_ticket_counts(events)
    save_ticket_counts(ticket_counts)


if __name__ == "__main__":
    main()
