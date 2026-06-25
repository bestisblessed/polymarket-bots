#!/usr/bin/env python3
"""Export the largest currently reachable public /trades set and merge it."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests


DATA_API = "https://data-api.polymarket.com"
DEFAULT_WALLET = "0x5a218c7ad04135830a45c41aaed7294df7809318"
WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "data" / "polymarket_balthazar"
PAGE_LIMIT = 1000
OFFSETS = [0, 1000, 2000, 3000]


def timestamp_to_iso(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return str(value)


def decimal_value(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def request_trades(session: requests.Session, params: dict[str, Any]) -> tuple[int, Any, str]:
    for attempt in range(6):
        response = session.get(f"{DATA_API}/trades", params=params, timeout=60)
        if response.status_code in {408, 429, 500, 502, 503, 504} and attempt < 5:
            print(
                f"retry status={response.status_code} side={params.get('side', 'ALL')} "
                f"offset={params.get('offset')} attempt={attempt + 1}",
                flush=True,
            )
            time.sleep(2 * (attempt + 1))
            continue
        if not response.ok:
            return response.status_code, None, response.text[:500]
        payload = response.json()
        if not isinstance(payload, list):
            return response.status_code, None, f"unexpected payload: {type(payload).__name__}"
        return response.status_code, payload, response.text[:500]
    return 0, None, "retry loop exhausted"


def fetch_segment(session: requests.Session, wallet: str, side: str | None, raw_dir: Path) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    pages: list[dict] = []
    segment_name = side or "ALL"
    for offset in OFFSETS:
        params: dict[str, Any] = {
            "user": wallet,
            "takerOnly": "false",
            "limit": PAGE_LIMIT,
            "offset": offset,
        }
        if side:
            params["side"] = side
        status, payload, response_text = request_trades(session, params)
        if payload is None:
            pages.append({"offset": offset, "count": 0, "status": status, "response_text": response_text})
            break
        write_json(raw_dir / f"{segment_name.lower()}_offset_{offset}.json", payload)
        rows.extend(payload)
        pages.append({"offset": offset, "count": len(payload), "status": status})
        print(f"segment={segment_name} offset={offset} count={len(payload)}", flush=True)
        if len(payload) < PAGE_LIMIT:
            break
    hit_cap = pages and pages[-1]["offset"] == OFFSETS[-1] and pages[-1]["count"] == PAGE_LIMIT
    return rows, {"segment": segment_name, "rows": len(rows), "pages": pages, "hit_public_cap": bool(hit_cap)}


def dedupe_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("transactionHash"),
        row.get("timestamp"),
        row.get("conditionId"),
        row.get("asset"),
        row.get("side"),
        row.get("outcomeIndex"),
        row.get("size"),
        row.get("price"),
    )


def normalize(row: dict[str, Any], sources: list[str]) -> dict[str, Any]:
    size = decimal_value(row.get("size"))
    price = decimal_value(row.get("price"))
    return {
        "timestamp": row.get("timestamp"),
        "datetime_utc": timestamp_to_iso(row.get("timestamp")),
        "side": row.get("side"),
        "condition_id": row.get("conditionId"),
        "asset": row.get("asset"),
        "market_title": row.get("title"),
        "event_slug": row.get("eventSlug"),
        "market_slug": row.get("slug"),
        "outcome": row.get("outcome"),
        "outcome_index": row.get("outcomeIndex"),
        "size": row.get("size"),
        "price": row.get("price"),
        "cash_size_est": str(size * price),
        "transaction_hash": row.get("transactionHash"),
        "sources": sources,
        "raw": row,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wallet", default=DEFAULT_WALLET)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    wallet = args.wallet.lower()
    if not WALLET_RE.match(wallet):
        raise ValueError(f"Invalid wallet address: {args.wallet}")

    session = requests.Session()
    session.headers.update({"User-Agent": "polymarket-bots-public-cap-trades-export/1.0"})
    raw_dir = args.out_dir / "raw" / "trades_public_cap"
    raw_dir.mkdir(parents=True, exist_ok=True)

    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    sources_by_key: dict[tuple[Any, ...], list[str]] = {}
    segment_meta: list[dict] = []
    for side in [None, "BUY", "SELL"]:
        rows, meta = fetch_segment(session, wallet, side, raw_dir)
        segment_meta.append(meta)
        segment = meta["segment"]
        for row in rows:
            key = dedupe_key(row)
            by_key.setdefault(key, row)
            sources_by_key.setdefault(key, []).append(segment)

    normalized = [
        normalize(row, sorted(set(sources_by_key[key])))
        for key, row in by_key.items()
    ]
    normalized.sort(key=lambda item: item.get("timestamp") or 0, reverse=True)

    fields = [
        "datetime_utc",
        "timestamp",
        "side",
        "market_title",
        "outcome",
        "size",
        "price",
        "cash_size_est",
        "condition_id",
        "event_slug",
        "market_slug",
        "transaction_hash",
        "sources",
    ]
    write_json(args.out_dir / "trade_transactions_public_cap_master.json", normalized)
    write_jsonl(args.out_dir / "trade_transactions_public_cap_master.jsonl", normalized)
    write_csv(args.out_dir / "trade_transactions_public_cap_master.csv", normalized, fields)

    summary = {
        "wallet": wallet,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "endpoint": f"{DATA_API}/trades",
        "docs": ["https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets"],
        "segments": segment_meta,
        "unique_rows": len(normalized),
        "raw_rows_across_segments": sum(meta["rows"] for meta in segment_meta),
        "duplicate_overlap_rows": sum(meta["rows"] for meta in segment_meta) - len(normalized),
        "newest_datetime_utc": normalized[0]["datetime_utc"] if normalized else "",
        "oldest_datetime_utc": normalized[-1]["datetime_utc"] if normalized else "",
        "newest_timestamp": normalized[0]["timestamp"] if normalized else None,
        "oldest_timestamp": normalized[-1]["timestamp"] if normalized else None,
        "is_full_history": not any(meta["hit_public_cap"] for meta in segment_meta),
        "limitation": "Side/all segments that hit offset 3000 with a full page may have older rows unavailable through /trades.",
    }
    write_json(args.out_dir / "trade_transactions_public_cap_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
