#!/usr/bin/env python3
"""Export public Polymarket wallet activity for correlation analysis."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests


DATA_API = "https://data-api.polymarket.com"
DEFAULT_WALLET = "0x5a218c7ad04135830a45c41aaed7294df7809318"
WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


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


def request_json(session: requests.Session, path: str, params: dict[str, Any]) -> Any:
    url = f"{DATA_API}{path}"
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = session.get(url, params=params, timeout=30)
            if response.status_code in {408, 429, 500, 502, 503, 504} and attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    if last_error:
        raise last_error
    raise RuntimeError(f"Request failed without response: {url}")


def fetch_list_pages(
    session: requests.Session,
    path: str,
    params: dict[str, Any],
    *,
    page_limit: int,
    max_offset: int,
    delay_s: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    offset = 0

    while offset <= max_offset:
        page_params = {**params, "limit": page_limit, "offset": offset}
        try:
            page = request_json(session, path, page_params)
        except requests.HTTPError as exc:
            if not rows:
                raise
            response = exc.response
            pages.append({"offset": offset, "count": 0, "error": str(exc)})
            return rows, {
                "complete": False,
                "pages": pages,
                "next_offset": offset,
                "stop_reason": "http_error_after_partial",
                "error": str(exc),
                "status_code": response.status_code if response is not None else None,
                "response_text": response.text[:500] if response is not None else "",
            }
        if not isinstance(page, list):
            raise ValueError(f"{path} returned {type(page).__name__}, expected list")

        pages.append({"offset": offset, "count": len(page)})
        rows.extend(page)
        print(f"{path} offset={offset} count={len(page)}", flush=True)

        if len(page) < page_limit:
            return rows, {
                "complete": True,
                "pages": pages,
                "next_offset": None,
                "stop_reason": "last_page_under_limit",
            }
        offset += page_limit
        if delay_s:
            time.sleep(delay_s)

    return rows, {
        "complete": False,
        "pages": pages,
        "next_offset": offset,
        "stop_reason": "max_offset_reached",
    }


def fetch_object_pages(
    session: requests.Session,
    path: str,
    params: dict[str, Any],
    *,
    data_key: str,
    page_limit: int,
    max_offset: int,
    delay_s: float,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    raw_pages: list[dict[str, Any]] = []
    offset = 0

    while offset <= max_offset:
        page_params = {**params, "limit": page_limit, "offset": offset}
        try:
            page = request_json(session, path, page_params)
        except requests.HTTPError as exc:
            if not rows:
                raise
            response = exc.response
            pages.append({"offset": offset, "count": 0, "error": str(exc)})
            return rows, {
                "complete": False,
                "pages": pages,
                "next_offset": offset,
                "stop_reason": "http_error_after_partial",
                "error": str(exc),
                "status_code": response.status_code if response is not None else None,
                "response_text": response.text[:500] if response is not None else "",
            }, raw_pages
        if not isinstance(page, dict):
            raise ValueError(f"{path} returned {type(page).__name__}, expected object")
        raw_pages.append(page)
        page_rows = page.get(data_key) or []
        if not isinstance(page_rows, list):
            raise ValueError(f"{path}.{data_key} returned {type(page_rows).__name__}, expected list")

        pagination = page.get("pagination") or {}
        pages.append({"offset": offset, "count": len(page_rows), "pagination": pagination})
        rows.extend(page_rows)
        print(f"{path} offset={offset} count={len(page_rows)}", flush=True)

        has_more = pagination.get("has_more")
        if has_more is False or len(page_rows) < page_limit:
            return rows, {
                "complete": True,
                "pages": pages,
                "next_offset": None,
                "stop_reason": "pagination_complete",
            }, raw_pages
        offset += page_limit
        if delay_s:
            time.sleep(delay_s)

    return rows, {
        "complete": False,
        "pages": pages,
        "next_offset": offset,
        "stop_reason": "max_offset_reached",
    }, raw_pages


def normalize_activity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        usdc_size = decimal_value(row.get("usdcSize"))
        normalized.append(
            {
                "timestamp": row.get("timestamp"),
                "datetime_utc": timestamp_to_iso(row.get("timestamp")),
                "type": row.get("type"),
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
                "transaction_hash": row.get("transactionHash"),
                "is_combo": row.get("isCombo", False),
                "raw": row,
            }
        )
    normalized.sort(key=lambda item: item.get("timestamp") or 0, reverse=True)
    return normalized


def normalize_trades(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
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
                "cash_size_est": str(decimal_value(row.get("size")) * decimal_value(row.get("price"))),
                "transaction_hash": row.get("transactionHash"),
                "raw": row,
            }
        )
    normalized.sort(key=lambda item: item.get("timestamp") or 0, reverse=True)
    return normalized


def normalize_positions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "condition_id": row.get("conditionId"),
                "asset": row.get("asset"),
                "market_title": row.get("title"),
                "event_slug": row.get("eventSlug"),
                "market_slug": row.get("slug"),
                "outcome": row.get("outcome"),
                "outcome_index": row.get("outcomeIndex"),
                "size": row.get("size"),
                "avg_price": row.get("avgPrice"),
                "cur_price": row.get("curPrice"),
                "initial_value": row.get("initialValue"),
                "current_value": row.get("currentValue"),
                "cash_pnl": row.get("cashPnl"),
                "percent_pnl": row.get("percentPnl"),
                "total_bought": row.get("totalBought"),
                "realized_pnl": row.get("realizedPnl"),
                "percent_realized_pnl": row.get("percentRealizedPnl"),
                "end_date": row.get("endDate"),
                "redeemable": row.get("redeemable"),
                "mergeable": row.get("mergeable"),
                "negative_risk": row.get("negativeRisk"),
                "raw": row,
            }
        )
    normalized.sort(key=lambda item: decimal_value(item.get("current_value")), reverse=True)
    return normalized


def normalize_closed_positions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "timestamp": row.get("timestamp"),
                "datetime_utc": timestamp_to_iso(row.get("timestamp")),
                "condition_id": row.get("conditionId"),
                "asset": row.get("asset"),
                "market_title": row.get("title"),
                "event_slug": row.get("eventSlug"),
                "market_slug": row.get("slug"),
                "outcome": row.get("outcome"),
                "outcome_index": row.get("outcomeIndex"),
                "avg_price": row.get("avgPrice"),
                "cur_price": row.get("curPrice"),
                "total_bought": row.get("totalBought"),
                "realized_pnl": row.get("realizedPnl"),
                "end_date": row.get("endDate"),
                "raw": row,
            }
        )
    normalized.sort(key=lambda item: item.get("timestamp") or 0, reverse=True)
    return normalized


def summarize_activity(activity: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in activity:
        key = (
            row.get("condition_id") or "",
            row.get("outcome") or "",
            row.get("side") or "",
        )
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

    summary: list[dict[str, Any]] = []
    for item in grouped.values():
        hashes = sorted(item.pop("transaction_hashes"))
        item["total_usdc_size"] = str(item["total_usdc_size"])
        item["total_tokens"] = str(item["total_tokens"])
        item["first_datetime_utc"] = timestamp_to_iso(item["first_timestamp"])
        item["last_datetime_utc"] = timestamp_to_iso(item["last_timestamp"])
        item["unique_transactions"] = len(hashes)
        item["sample_transaction_hashes"] = ";".join(hashes[:5])
        summary.append(item)
    summary.sort(key=lambda item: decimal_value(item.get("total_usdc_size")), reverse=True)
    return summary


def build_correlation_timeline(
    activity: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    x_tweets_path: Path | None,
) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    seen_trade_keys: set[tuple[Any, Any, Any, Any]] = set()

    for row in activity:
        timeline.append(
            {
                "source": "polymarket_activity",
                "timestamp": row.get("timestamp"),
                "datetime_utc": row.get("datetime_utc"),
                "title": row.get("market_title"),
                "side": row.get("side"),
                "outcome": row.get("outcome"),
                "amount": row.get("usdc_size"),
                "condition_id": row.get("condition_id"),
                "transaction_hash": row.get("transaction_hash"),
                "text": "",
                "url": "",
            }
        )
        seen_trade_keys.add(
            (
                row.get("transaction_hash"),
                row.get("condition_id"),
                row.get("side"),
                row.get("outcome"),
            )
        )

    for row in trades:
        key = (
            row.get("transaction_hash"),
            row.get("condition_id"),
            row.get("side"),
            row.get("outcome"),
        )
        if key in seen_trade_keys:
            continue
        timeline.append(
            {
                "source": "polymarket_trade",
                "timestamp": row.get("timestamp"),
                "datetime_utc": row.get("datetime_utc"),
                "title": row.get("market_title"),
                "side": row.get("side"),
                "outcome": row.get("outcome"),
                "amount": row.get("cash_size_est"),
                "condition_id": row.get("condition_id"),
                "transaction_hash": row.get("transaction_hash"),
                "text": "",
                "url": "",
            }
        )

    if x_tweets_path and x_tweets_path.exists():
        tweets = json.loads(x_tweets_path.read_text())
        for tweet in tweets:
            created_at = tweet.get("created_at") or ""
            timestamp = ""
            try:
                timestamp = int(datetime.fromisoformat(created_at).timestamp())
            except (TypeError, ValueError):
                pass
            timeline.append(
                {
                    "source": "x_tweet",
                    "timestamp": timestamp,
                    "datetime_utc": created_at,
                    "title": "",
                    "side": "",
                    "outcome": "",
                    "amount": "",
                    "condition_id": "",
                    "transaction_hash": "",
                    "text": tweet.get("text", ""),
                    "url": tweet.get("url", ""),
                }
            )

    timeline.sort(key=lambda item: item.get("timestamp") or 0, reverse=True)
    return timeline


def write_outputs(out_dir: Path, name: str, rows: list[dict[str, Any]], fields: list[str]) -> None:
    write_json(out_dir / f"{name}.json", rows)
    write_jsonl(out_dir / f"{name}.jsonl", rows)
    write_csv(out_dir / f"{name}.csv", rows, fields)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wallet", default=DEFAULT_WALLET)
    parser.add_argument("--out-dir", type=Path, default=Path("my-correlation-bot-v1/data/polymarket_balthazar"))
    parser.add_argument("--x-tweets", type=Path, default=Path("my-correlation-bot-v1/data/x_balthazarpoly/tweets_combined.json"))
    parser.add_argument("--page-limit", type=int, default=500)
    parser.add_argument("--max-offset", type=int, default=10000)
    parser.add_argument("--delay-s", type=float, default=0.15)
    args = parser.parse_args()

    wallet = args.wallet.lower()
    if not WALLET_RE.match(wallet):
        raise ValueError(f"Invalid wallet address: {args.wallet}")

    raw_dir = args.out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": "polymarket-bots-correlation-export/1.0"})
    captured_at = utc_now()

    metadata: dict[str, Any] = {
        "wallet": wallet,
        "captured_at": captured_at,
        "data_api": DATA_API,
        "page_limit": args.page_limit,
        "max_offset": args.max_offset,
        "endpoints": {},
        "docs": [
            "https://docs.polymarket.com/api-reference/core/get-user-activity",
            "https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets",
            "https://docs.polymarket.com/api-reference/core/get-current-positions-for-a-user",
            "https://docs.polymarket.com/api-reference/core/get-closed-positions-for-a-user",
            "https://docs.polymarket.com/api-reference/core/get-total-value-of-a-users-positions",
            "https://docs.polymarket.com/api-reference/core/get-user-combo-positions",
            "https://docs.polymarket.com/api-reference/core/get-user-combo-activity",
        ],
    }

    activity_raw, activity_meta = fetch_list_pages(
        session,
        "/activity",
        {"user": wallet, "sortBy": "TIMESTAMP", "sortDirection": "DESC"},
        page_limit=min(args.page_limit, 500),
        max_offset=args.max_offset,
        delay_s=args.delay_s,
    )
    metadata["endpoints"]["activity"] = activity_meta
    write_json(raw_dir / "activity.json", activity_raw)

    trades_raw, trades_meta = fetch_list_pages(
        session,
        "/trades",
        {"user": wallet, "takerOnly": "false"},
        page_limit=min(args.page_limit, 500),
        max_offset=args.max_offset,
        delay_s=args.delay_s,
    )
    metadata["endpoints"]["trades"] = trades_meta
    write_json(raw_dir / "trades.json", trades_raw)

    positions_raw, positions_meta = fetch_list_pages(
        session,
        "/positions",
        {"user": wallet, "sizeThreshold": 0, "sortBy": "CURRENT", "sortDirection": "DESC"},
        page_limit=min(args.page_limit, 500),
        max_offset=args.max_offset,
        delay_s=args.delay_s,
    )
    metadata["endpoints"]["positions"] = positions_meta
    write_json(raw_dir / "positions.json", positions_raw)

    closed_raw, closed_meta = fetch_list_pages(
        session,
        "/closed-positions",
        {"user": wallet, "sortBy": "TIMESTAMP", "sortDirection": "DESC"},
        page_limit=50,
        max_offset=100000,
        delay_s=args.delay_s,
    )
    metadata["endpoints"]["closed_positions"] = closed_meta
    write_json(raw_dir / "closed_positions.json", closed_raw)

    value_raw = request_json(session, "/value", {"user": wallet})
    metadata["endpoints"]["value"] = {"complete": True, "count": len(value_raw) if isinstance(value_raw, list) else 1}
    write_json(raw_dir / "value.json", value_raw)

    try:
        combo_positions_raw, combo_positions_meta, combo_positions_pages = fetch_object_pages(
            session,
            "/v1/positions/combos",
            {"user": wallet, "sort": "current_value_desc"},
            page_limit=100,
            max_offset=args.max_offset,
            delay_s=args.delay_s,
            data_key="combos",
        )
        metadata["endpoints"]["combo_positions"] = combo_positions_meta
        write_json(raw_dir / "combo_positions.json", combo_positions_raw)
        write_json(raw_dir / "combo_positions_pages.json", combo_positions_pages)
    except requests.HTTPError as exc:
        metadata["endpoints"]["combo_positions"] = {"complete": False, "error": str(exc)}
        combo_positions_raw = []

    try:
        combo_activity_raw, combo_activity_meta, combo_activity_pages = fetch_object_pages(
            session,
            "/v1/activity/combos",
            {"user": wallet},
            page_limit=500,
            max_offset=args.max_offset,
            delay_s=args.delay_s,
            data_key="activity",
        )
        metadata["endpoints"]["combo_activity"] = combo_activity_meta
        write_json(raw_dir / "combo_activity.json", combo_activity_raw)
        write_json(raw_dir / "combo_activity_pages.json", combo_activity_pages)
    except requests.HTTPError as exc:
        metadata["endpoints"]["combo_activity"] = {"complete": False, "error": str(exc)}
        combo_activity_raw = []

    activity = normalize_activity(activity_raw)
    trades = normalize_trades(trades_raw)
    positions = normalize_positions(positions_raw)
    closed_positions = normalize_closed_positions(closed_raw)
    market_summary = summarize_activity([row for row in activity if row.get("type") == "TRADE"])
    timeline = build_correlation_timeline(activity, trades, args.x_tweets)

    activity_fields = [
        "datetime_utc",
        "timestamp",
        "type",
        "side",
        "market_title",
        "outcome",
        "size",
        "price",
        "usdc_size",
        "condition_id",
        "event_slug",
        "market_slug",
        "transaction_hash",
        "is_combo",
    ]
    trade_fields = [
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
    ]
    position_fields = [
        "market_title",
        "outcome",
        "size",
        "avg_price",
        "cur_price",
        "initial_value",
        "current_value",
        "cash_pnl",
        "percent_pnl",
        "total_bought",
        "realized_pnl",
        "condition_id",
        "event_slug",
        "market_slug",
        "end_date",
    ]
    closed_fields = [
        "datetime_utc",
        "timestamp",
        "market_title",
        "outcome",
        "avg_price",
        "cur_price",
        "total_bought",
        "realized_pnl",
        "condition_id",
        "event_slug",
        "market_slug",
        "end_date",
    ]
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
    timeline_fields = [
        "source",
        "datetime_utc",
        "timestamp",
        "title",
        "side",
        "outcome",
        "amount",
        "condition_id",
        "transaction_hash",
        "text",
        "url",
    ]

    write_outputs(args.out_dir, "activity", activity, activity_fields)
    write_outputs(args.out_dir, "trades", trades, trade_fields)
    write_outputs(args.out_dir, "positions_current", positions, position_fields)
    write_outputs(args.out_dir, "closed_positions", closed_positions, closed_fields)
    write_outputs(args.out_dir, "activity_market_summary", market_summary, summary_fields)
    write_csv(args.out_dir / "correlation_timeline.csv", timeline, timeline_fields)
    write_json(args.out_dir / "combo_positions.json", combo_positions_raw)
    write_json(args.out_dir / "combo_activity.json", combo_activity_raw)

    activity_by_type = defaultdict(int)
    activity_by_side = defaultdict(int)
    for row in activity:
        activity_by_type[row.get("type") or "UNKNOWN"] += 1
        activity_by_side[row.get("side") or "UNKNOWN"] += 1

    summary = {
        "wallet": wallet,
        "captured_at": captured_at,
        "activity_rows": len(activity),
        "activity_by_type": dict(sorted(activity_by_type.items())),
        "activity_by_side": dict(sorted(activity_by_side.items())),
        "trade_rows": len(trades),
        "current_positions": len(positions),
        "closed_positions": len(closed_positions),
        "combo_positions": len(combo_positions_raw),
        "combo_activity": len(combo_activity_raw),
        "markets_in_trade_activity": len({row.get("condition_id") for row in activity if row.get("condition_id")}),
        "value": value_raw,
        "timeline_rows": len(timeline),
        "metadata_file": "metadata.json",
    }
    write_json(args.out_dir / "summary.json", summary)
    write_json(args.out_dir / "metadata.json", metadata)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
