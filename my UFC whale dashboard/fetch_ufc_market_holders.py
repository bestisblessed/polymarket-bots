#!/usr/bin/env python3
"""
Fetch top holders for all markets in UFC events and save to files.

Default behavior:
  - If no slugs are provided, uses get_ufc_event_slugs.py in this directory.
  - For each event slug, fetches the event from Gamma and then fetches the top
    holders for every market conditionId via the Data API /holders endpoint.

Examples:
  python3 fetch_ufc_market_holders.py ufc-ale14-die4-2026-01-31
  python3 fetch_ufc_market_holders.py ufc-ale14-die4-2026-01-31 ufc-raf-mau4-2026-01-31
  python3 fetch_ufc_market_holders.py --limit 20 --min-balance 1
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API_HOLDERS = "https://data-api.polymarket.com/holders"

DEFAULT_LIMIT = 20  # Per docs, max 20
DEFAULT_MIN_BALANCE = 1

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "ufc-holders"
SLUG_SCRIPT = Path(__file__).with_name("get_ufc_event_slugs.py")


def parse_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            return [value]
    return []


def to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run_slug_script() -> List[str]:
    if not SLUG_SCRIPT.exists():
        raise FileNotFoundError(f"Slug script not found: {SLUG_SCRIPT}")
    result = subprocess.run(
        [sys.executable, str(SLUG_SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def fetch_event_by_slug(session: requests.Session, slug: str) -> Dict[str, Any]:
    url = f"{GAMMA_API}/events/slug/{slug}"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_holders_for_market(
    session: requests.Session,
    condition_id: str,
    *,
    limit: int,
    min_balance: Optional[int],
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"market": condition_id, "limit": limit}
    if min_balance is not None:
        params["minBalance"] = min_balance
    resp = session.get(DATA_API_HOLDERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json() or []


def build_market_payload(
    *,
    event: Dict[str, Any],
    market: Dict[str, Any],
    holders_payload: List[Dict[str, Any]],
    fetched_at: str,
) -> Dict[str, Any]:
    outcomes = parse_list(market.get("outcomes") or [])
    prices_raw = parse_list(market.get("outcomePrices") or [])
    prices = [to_float(p) for p in prices_raw]

    tokens: List[Dict[str, Any]] = []
    for token_entry in holders_payload:
        holders = token_entry.get("holders") or []
        outcome_idx = holders[0].get("outcomeIndex") if holders else None
        outcome_name = (
            outcomes[outcome_idx]
            if isinstance(outcome_idx, int) and outcome_idx < len(outcomes)
            else str(outcome_idx)
        )
        price = (
            float(prices[outcome_idx])
            if isinstance(outcome_idx, int) and outcome_idx < len(prices) and prices[outcome_idx] is not None
            else None
        )
        tokens.append(
            {
                "token": token_entry.get("token"),
                "outcomeIndex": outcome_idx,
                "outcome": outcome_name,
                "price": price,
                "holders": holders,
            }
        )

    return {
        "fetchedAt": fetched_at,
        "event": {
            "id": event.get("id"),
            "slug": event.get("slug"),
            "title": event.get("title"),
            "url": f"https://polymarket.com/event/{event.get('slug')}",
        },
        "market": {
            "id": market.get("id"),
            "conditionId": market.get("conditionId"),
            "slug": market.get("slug"),
            "question": market.get("question"),
            "groupItemTitle": market.get("groupItemTitle"),
            "sportsMarketType": market.get("sportsMarketType"),
            "outcomes": outcomes,
            "outcomePrices": prices,
        },
        "tokens": tokens,
    }


def build_flat_rows(
    *,
    event: Dict[str, Any],
    market: Dict[str, Any],
    token_entries: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    outcomes = parse_list(market.get("outcomes") or [])
    prices_raw = parse_list(market.get("outcomePrices") or [])
    prices = [to_float(p) for p in prices_raw]

    for token_entry in token_entries:
        holders = token_entry.get("holders") or []
        outcome_idx = holders[0].get("outcomeIndex") if holders else None
        outcome_name = (
            outcomes[outcome_idx]
            if isinstance(outcome_idx, int) and outcome_idx < len(outcomes)
            else str(outcome_idx)
        )
        price = (
            float(prices[outcome_idx])
            if isinstance(outcome_idx, int) and outcome_idx < len(prices) and prices[outcome_idx] is not None
            else None
        )
        for holder in holders:
            wallet = holder.get("proxyWallet")
            shares = to_float(holder.get("amount"))
            if not wallet or shares is None:
                continue
            approx_usd = shares * price if price is not None else None
            identity = holder.get("name") or holder.get("pseudonym") or wallet
            rows.append(
                {
                    "event_slug": event.get("slug"),
                    "event_title": event.get("title"),
                    "market_id": market.get("id"),
                    "condition_id": market.get("conditionId"),
                    "market_slug": market.get("slug"),
                    "market_question": market.get("question"),
                    "sports_market_type": market.get("sportsMarketType"),
                    "group_item_title": market.get("groupItemTitle"),
                    "token": token_entry.get("token"),
                    "outcome_index": outcome_idx,
                    "outcome": outcome_name,
                    "price": price,
                    "holder": identity,
                    "wallet": wallet,
                    "shares": shares,
                    "approx_usd": approx_usd,
                }
            )
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def collect_event_holders(
    session: requests.Session,
    *,
    event_slug: str,
    limit: int,
    min_balance: Optional[int],
    output_dir: Path,
) -> Dict[str, Any]:
    event = fetch_event_by_slug(session, event_slug)
    markets = event.get("markets") or []
    fetched_at = datetime.now(timezone.utc).isoformat()
    market_payloads: List[Dict[str, Any]] = []
    flat_rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    print(f"[INFO] Event {event_slug}: {len(markets)} markets")
    for idx, market in enumerate(markets, start=1):
        condition_id = market.get("conditionId")
        if not condition_id:
            errors.append(
                {
                    "market_id": market.get("id"),
                    "market_slug": market.get("slug"),
                    "error": "missing conditionId",
                }
            )
            continue

        try:
            holders_payload = fetch_holders_for_market(
                session,
                condition_id,
                limit=limit,
                min_balance=min_balance,
            )
        except Exception as exc:
            errors.append(
                {
                    "market_id": market.get("id"),
                    "market_slug": market.get("slug"),
                    "conditionId": condition_id,
                    "error": str(exc),
                }
            )
            continue

        market_payloads.append(
            build_market_payload(
                event=event,
                market=market,
                holders_payload=holders_payload,
                fetched_at=fetched_at,
            )
        )
        flat_rows.extend(
            build_flat_rows(
                event=event,
                market=market,
                token_entries=holders_payload,
            )
        )
        if idx % 10 == 0:
            print(f"  - processed {idx}/{len(markets)} markets")

    event_output_dir = output_dir / event_slug
    write_json(event_output_dir / "holders.json", market_payloads)
    write_csv(event_output_dir / "holders_flat.csv", flat_rows)
    if errors:
        write_json(event_output_dir / "errors.json", errors)

    return {
        "event_slug": event_slug,
        "markets": len(markets),
        "market_outputs": len(market_payloads),
        "rows": len(flat_rows),
        "errors": len(errors),
        "output_dir": str(event_output_dir),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch top holders for all markets in UFC events."
    )
    parser.add_argument(
        "slugs",
        nargs="*",
        help="Event slugs to process (default: from get_ufc_event_slugs.py)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Top holders per outcome (max 20 per docs)",
    )
    parser.add_argument(
        "--min-balance",
        type=int,
        default=DEFAULT_MIN_BALANCE,
        help="Minimum balance filter for holders",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help="Output directory for files",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit < 1 or args.limit > 20:
        raise ValueError("limit must be between 1 and 20 (Data API cap)")

    slugs = [s.strip() for s in args.slugs if s.strip()]
    if not slugs:
        print("[INFO] No slugs provided, using get_ufc_event_slugs.py")
        slugs = run_slug_script()

    if not slugs:
        print("[ERROR] No event slugs found")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    session = requests.Session()

    summaries = []
    for slug in slugs:
        try:
            summary = collect_event_holders(
                session,
                event_slug=slug,
                limit=args.limit,
                min_balance=args.min_balance,
                output_dir=output_dir,
            )
            summaries.append(summary)
        except Exception as exc:
            summaries.append(
                {
                    "event_slug": slug,
                    "error": str(exc),
                }
            )

    write_json(output_dir / "run_summary.json", summaries)
    print(f"[INFO] Wrote summary: {output_dir / 'run_summary.json'}")


if __name__ == "__main__":
    main()
