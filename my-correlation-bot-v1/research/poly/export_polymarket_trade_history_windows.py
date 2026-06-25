#!/usr/bin/env python3
"""Export full public Polymarket TRADE activity using timestamp windows."""

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
PAGE_LIMIT = 500
MAX_LIVE_OFFSET = 3000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def request_activity(session: requests.Session, params: dict[str, Any]) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            response = session.get(f"{DATA_API}/activity", params=params, timeout=30)
            if response.status_code in {408, 429, 500, 502, 503, 504} and attempt < 7:
                print(
                    f"retry status={response.status_code} offset={params.get('offset')} "
                    f"end={params.get('end', 'latest')} attempt={attempt + 1}",
                    flush=True,
                )
                time.sleep(2.0 * (attempt + 1))
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError(f"Unexpected /activity response: {type(payload).__name__}")
            return payload
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt == 7:
                raise
            time.sleep(1.5 * (attempt + 1))
    if last_error:
        raise last_error
    raise RuntimeError("Request failed without response")


def fetch_window(
    session: requests.Session,
    wallet: str,
    *,
    end_ts: int | None,
    delay_s: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    complete = False
    for offset in range(0, MAX_LIVE_OFFSET + 1, PAGE_LIMIT):
        params: dict[str, Any] = {
            "user": wallet,
            "type": "TRADE",
            "sortBy": "TIMESTAMP",
            "sortDirection": "DESC",
            "limit": PAGE_LIMIT,
            "offset": offset,
        }
        if end_ts is not None:
            params["end"] = end_ts
        page = request_activity(session, params)
        rows.extend(page)
        pages.append({"offset": offset, "count": len(page)})
        print(f"window_end={end_ts or 'latest'} offset={offset} count={len(page)}", flush=True)
        if len(page) < PAGE_LIMIT:
            complete = True
            break
        if delay_s:
            time.sleep(delay_s)

    timestamps = [int(row["timestamp"]) for row in rows if row.get("timestamp") is not None]
    metadata = {
        "end": end_ts,
        "rows": len(rows),
        "complete": complete,
        "pages": pages,
        "newest_timestamp": max(timestamps) if timestamps else None,
        "oldest_timestamp": min(timestamps) if timestamps else None,
        "newest_datetime_utc": timestamp_to_iso(max(timestamps)) if timestamps else "",
        "oldest_datetime_utc": timestamp_to_iso(min(timestamps)) if timestamps else "",
        "stop_reason": "short_page" if complete else "live_offset_cap",
    }
    return rows, metadata


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


def normalize_trade(row: dict[str, Any], source_windows: list[int]) -> dict[str, Any]:
    usdc_size = decimal_value(row.get("usdcSize"))
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
        "usdc_size": str(usdc_size),
        "cash_size_est": str(size * price),
        "transaction_hash": row.get("transactionHash"),
        "is_combo": row.get("isCombo", False),
        "source_windows": source_windows,
        "raw": row,
    }


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row.get("condition_id") or "", row.get("outcome") or "", row.get("side") or "")
        item = grouped.setdefault(
            key,
            {
                "condition_id": row.get("condition_id"),
                "market_title": row.get("market_title"),
                "event_slug": row.get("event_slug"),
                "market_slug": row.get("market_slug"),
                "outcome": row.get("outcome"),
                "side": row.get("side"),
                "trade_count": 0,
                "total_usdc_size": Decimal("0"),
                "total_tokens": Decimal("0"),
                "first_timestamp": row.get("timestamp"),
                "last_timestamp": row.get("timestamp"),
                "transaction_hashes": set(),
            },
        )
        item["trade_count"] += 1
        item["total_usdc_size"] += decimal_value(row.get("usdc_size"))
        item["total_tokens"] += decimal_value(row.get("size"))
        item["first_timestamp"] = min(item["first_timestamp"] or row.get("timestamp"), row.get("timestamp") or 0)
        item["last_timestamp"] = max(item["last_timestamp"] or row.get("timestamp"), row.get("timestamp") or 0)
        if row.get("transaction_hash"):
            item["transaction_hashes"].add(row["transaction_hash"])

    output: list[dict[str, Any]] = []
    for item in grouped.values():
        hashes = sorted(item.pop("transaction_hashes"))
        item["total_usdc_size"] = str(item["total_usdc_size"])
        item["total_tokens"] = str(item["total_tokens"])
        item["first_datetime_utc"] = timestamp_to_iso(item["first_timestamp"])
        item["last_datetime_utc"] = timestamp_to_iso(item["last_timestamp"])
        item["unique_transactions"] = len(hashes)
        item["sample_transaction_hashes"] = ";".join(hashes[:5])
        output.append(item)
    output.sort(key=lambda item: decimal_value(item.get("total_usdc_size")), reverse=True)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wallet", default=DEFAULT_WALLET)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--delay-s", type=float, default=0.05)
    parser.add_argument("--max-windows", type=int, default=100)
    args = parser.parse_args()

    wallet = args.wallet.lower()
    if not WALLET_RE.match(wallet):
        raise ValueError(f"Invalid wallet address: {args.wallet}")

    session = requests.Session()
    session.headers.update({"User-Agent": "polymarket-bots-trade-history-export/1.0"})

    chunk_dir = args.out_dir / "raw" / "activity_trade_windows"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, Any] = {
        "wallet": wallet,
        "captured_at": utc_now(),
        "endpoint": f"{DATA_API}/activity",
        "params": {
            "type": "TRADE",
            "sortBy": "TIMESTAMP",
            "sortDirection": "DESC",
            "limit": PAGE_LIMIT,
            "max_live_offset": MAX_LIVE_OFFSET,
        },
        "docs": ["https://docs.polymarket.com/api-reference/core/get-user-activity"],
        "windows": [],
    }

    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    source_windows: dict[tuple[Any, ...], list[int]] = {}
    end_ts: int | None = None

    for window_index in range(args.max_windows):
        rows, window_meta = fetch_window(session, wallet, end_ts=end_ts, delay_s=args.delay_s)
        write_json(chunk_dir / f"window_{window_index:03d}.json", rows)
        window_meta["index"] = window_index
        metadata["windows"].append(window_meta)

        before = len(by_key)
        for row in rows:
            key = dedupe_key(row)
            by_key.setdefault(key, row)
            source_windows.setdefault(key, []).append(window_index)
        new_unique = len(by_key) - before
        window_meta["new_unique_rows"] = new_unique

        if not rows:
            metadata["complete"] = True
            metadata["stop_reason"] = "empty_window"
            break
        if window_meta["complete"]:
            metadata["complete"] = True
            metadata["stop_reason"] = "short_final_window"
            break

        oldest = window_meta["oldest_timestamp"]
        if oldest is None:
            metadata["complete"] = False
            metadata["stop_reason"] = "missing_oldest_timestamp"
            break

        next_end_ts = int(oldest)
        if end_ts == next_end_ts and new_unique == 0:
            next_end_ts -= 1
        end_ts = next_end_ts
    else:
        metadata["complete"] = False
        metadata["stop_reason"] = "max_windows_reached"

    normalized = [
        normalize_trade(row, sorted(set(source_windows[key])))
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
        "usdc_size",
        "cash_size_est",
        "condition_id",
        "event_slug",
        "market_slug",
        "transaction_hash",
        "is_combo",
        "source_windows",
    ]
    write_json(args.out_dir / "trade_transactions_master.json", normalized)
    write_jsonl(args.out_dir / "trade_transactions_master.jsonl", normalized)
    write_csv(args.out_dir / "trade_transactions_master.csv", normalized, fields)

    market_summary = summarize(normalized)
    summary_fields = [
        "market_title",
        "outcome",
        "side",
        "trade_count",
        "total_usdc_size",
        "total_tokens",
        "first_datetime_utc",
        "last_datetime_utc",
        "unique_transactions",
        "condition_id",
        "event_slug",
        "market_slug",
        "sample_transaction_hashes",
    ]
    write_json(args.out_dir / "trade_transactions_market_summary.json", market_summary)
    write_jsonl(args.out_dir / "trade_transactions_market_summary.jsonl", market_summary)
    write_csv(args.out_dir / "trade_transactions_market_summary.csv", market_summary, summary_fields)

    metadata["unique_rows"] = len(normalized)
    metadata["raw_rows_across_windows"] = sum(window["rows"] for window in metadata["windows"])
    metadata["duplicate_overlap_rows"] = metadata["raw_rows_across_windows"] - len(normalized)
    metadata["oldest_timestamp"] = normalized[-1]["timestamp"] if normalized else None
    metadata["oldest_datetime_utc"] = normalized[-1]["datetime_utc"] if normalized else ""
    metadata["newest_timestamp"] = normalized[0]["timestamp"] if normalized else None
    metadata["newest_datetime_utc"] = normalized[0]["datetime_utc"] if normalized else ""
    metadata["market_summary_rows"] = len(market_summary)
    write_json(args.out_dir / "trade_transactions_master_summary.json", metadata)
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
