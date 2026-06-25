#!/usr/bin/env python3
"""
Live UFC 99/1 odds monitor for Polymarket moneyline markets.

This bot only sends notifications. It does not place bets.
"""

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Optional

import requests
import websocket
from dotenv import load_dotenv


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
SPORTS_WS_URL = "wss://sports-api.polymarket.com/ws"
PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json"
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")

DEFAULT_ALERT_PRICE = 0.01
DEFAULT_HEARTBEAT_SECONDS = 300
DEFAULT_REQUIRE_SPORTS_LIVE = True

LIVE_STATUSES = {"inprogress", "running"}
ENDED_STATUSES = {
    "final",
    "f/ot",
    "f/so",
    "finished",
    "postponed",
    "canceled",
    "cancelled",
    "forfeit",
    "notnecessary",
    "awarded",
}


def parse_json_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except JSONDecodeError:
            return [value]
        return parsed if isinstance(parsed, list) else [parsed]
    return [value]


def to_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def best_ask_from_book(book: dict) -> Optional[float]:
    prices = [to_float(level.get("price")) for level in book.get("asks", []) if isinstance(level, dict)]
    prices = [price for price in prices if price is not None]
    return min(prices) if prices else None


def best_bid_from_book(book: dict) -> Optional[float]:
    prices = [to_float(level.get("price")) for level in book.get("bids", []) if isinstance(level, dict)]
    prices = [price for price in prices if price is not None]
    return max(prices) if prices else None


def should_alert(asset_id: str, ask_price: Optional[float], threshold: float, alerted_asset_ids: set) -> bool:
    return bool(asset_id) and ask_price is not None and ask_price <= threshold and asset_id not in alerted_asset_ids


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def value_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def sports_state_from_message(data: dict, received_at: Optional[datetime] = None) -> Optional[dict]:
    if not isinstance(data, dict):
        return None
    if data.get("event_type") not in {None, "sport_result"}:
        return None

    slug = str(data.get("slug") or "").strip().lower()
    if not slug:
        return None

    status = str(data.get("status") or "").strip()
    status_key = status.lower().replace(" ", "")
    ended = value_bool(data.get("ended")) or status_key in ENDED_STATUSES
    live = (value_bool(data.get("live")) or status_key in LIVE_STATUSES) and not ended

    return {
        "slug": slug,
        "live": live,
        "ended": ended,
        "status": status,
        "score": data.get("score"),
        "period": data.get("period"),
        "elapsed": data.get("elapsed"),
        "updated_at": received_at or datetime.now(timezone.utc),
    }


def is_live_alert_allowed(
    asset_id: str,
    info: dict,
    sports_states: dict,
    resolved_asset_ids: set,
    *,
    require_sports_live: bool,
    unsafe_ignore_live_gate: bool = False,
) -> tuple[bool, str]:
    if asset_id in resolved_asset_ids:
        return False, "market resolved"

    if info.get("event_closed") or info.get("event_archived"):
        return False, "event closed or archived"
    if info.get("market_closed") or info.get("market_archived"):
        return False, "market closed or archived"
    if info.get("market_active") is False:
        return False, "market inactive"
    if info.get("accepting_orders") is False:
        return False, "market not accepting orders"

    if unsafe_ignore_live_gate:
        return True, "live gate bypassed"

    slug = str(info.get("event_slug") or "").strip().lower()
    state = sports_states.get(slug)
    if state:
        if state.get("ended"):
            return False, f"sports ended ({state.get('status') or 'ended'})"
        if state.get("live"):
            return True, f"sports live ({state.get('status') or 'live'})"
        return False, f"sports not live ({state.get('status') or 'not live'})"

    if require_sports_live:
        return False, "waiting for sports live state"

    return True, "sports live state not required"


def format_price(price: Optional[float]) -> str:
    if price is None:
        return "n/a"
    return f"{price:.2f}"


def format_percent(price: Optional[float]) -> str:
    if price is None:
        return "n/a"
    return f"{price:.0%}"


def send_pushover(message: str, url: Optional[str], title: str, no_notify: bool) -> None:
    if no_notify:
        print("[NO_NOTIFY] Would send Pushover:")
        print(message)
        return

    token = os.environ.get("PUSHOVER_API_TOKEN")
    user = os.environ.get("PUSHOVER_GROUP_KEY")
    if not token or not user:
        print("[WARN] Pushover credentials not found, skipping notification")
        return

    payload = {
        "token": token,
        "user": user,
        "title": title,
        "message": message,
    }
    if url:
        payload["url"] = url
        payload["url_title"] = "Open Polymarket Event"

    try:
        resp = requests.post(PUSHOVER_ENDPOINT, data=payload, timeout=10)
        if resp.ok:
            print("[INFO] Pushover notification sent")
        else:
            print(f"[WARN] Pushover failed: {resp.status_code} {resp.text[:200]}")
    except requests.RequestException as exc:
        print(f"[WARN] Pushover error: {exc}")


def fetch_ufc_fight_events(limit: int = 200) -> list:
    events = []
    offset = 0

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
            timeout=60,
        )
        resp.raise_for_status()
        batch = resp.json() or []
        if not batch:
            break

        for event in batch:
            markets = event.get("markets") or []
            if any((market.get("sportsMarketType") or "") == "moneyline" for market in markets):
                events.append(event)

        offset += len(batch)

    return events


def find_event_by_slug_or_search(target: str) -> list:
    if (target or "").lower() == "all":
        return fetch_ufc_fight_events()

    resp = requests.get(f"{GAMMA_API}/events", params={"slug": target}, timeout=30)
    resp.raise_for_status()
    events = resp.json() or []
    if events:
        return events

    keywords = (target or "").lower().replace("-", " ").split()
    if not keywords:
        return []

    matches = []
    for event in fetch_ufc_fight_events():
        searchable = " ".join(
            [
                str(event.get("title") or ""),
                str(event.get("slug") or ""),
                " ".join(str(market.get("question") or "") for market in event.get("markets") or []),
            ]
        ).lower()
        if all(keyword in searchable for keyword in keywords):
            matches.append(event)
    return matches


def build_token_map(events: list) -> tuple[dict, list[str]]:
    token_map = {}
    token_ids = []

    for event in events:
        event_slug = event.get("slug") or "unknown"
        event_title = event.get("title") or event_slug
        event_url = f"https://polymarket.com/event/{event_slug}"

        for market in event.get("markets") or []:
            if (market.get("sportsMarketType") or "") != "moneyline":
                continue

            outcomes = parse_json_list(market.get("outcomes"))
            token_values = parse_json_list(market.get("clobTokenIds"))
            if len(token_values) < 2:
                continue

            fight_label = market.get("groupItemTitle") or market.get("question") or event_title

            for index, token_id in enumerate(token_values):
                if not token_id:
                    continue
                token_id = str(token_id)

                opponent = None
                if len(outcomes) == 2:
                    opponent = outcomes[1 - index] if index in (0, 1) else None

                token_map[token_id] = {
                    "event_slug": event_slug,
                    "event_title": event_title,
                    "event_url": event_url,
                    "event_closed": bool(event.get("closed")),
                    "event_archived": bool(event.get("archived")),
                    "fight_label": fight_label,
                    "market_title": market.get("question") or "Moneyline",
                    "market_active": market.get("active", True),
                    "market_closed": bool(market.get("closed")),
                    "market_archived": bool(market.get("archived")),
                    "accepting_orders": market.get("acceptingOrders"),
                    "enable_order_book": market.get("enableOrderBook"),
                    "condition_id": market.get("conditionId"),
                    "fighter": outcomes[index] if index < len(outcomes) else f"Outcome {index + 1}",
                    "opponent": opponent,
                }
                token_ids.append(token_id)

    seen = set()
    token_ids = [token_id for token_id in token_ids if not (token_id in seen or seen.add(token_id))]
    return token_map, token_ids


def group_tokens_by_slug(token_map: dict) -> dict:
    grouped = {}
    for token_id, info in token_map.items():
        slug = str(info.get("event_slug") or "").strip().lower()
        if slug:
            grouped.setdefault(slug, []).append(token_id)
    return grouped


def fetch_books(token_ids: list[str]) -> list[dict]:
    resp = requests.post(
        f"{CLOB_API}/books",
        json=[{"token_id": token_id} for token_id in token_ids],
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json() or []


def seed_books(
    token_ids: list[str],
    book_state: dict,
    token_map: dict,
    threshold: float,
    alerted_asset_ids: set,
    no_notify: bool,
    title: str,
    sports_states: dict,
    resolved_asset_ids: set,
    require_sports_live: bool,
    unsafe_ignore_live_gate: bool,
) -> None:
    print(f"[INFO] Seeding orderbooks for {len(token_ids)} tokens...")
    books = []
    for i in range(0, len(token_ids), 500):
        try:
            books.extend(fetch_books(token_ids[i : i + 500]))
        except requests.RequestException as exc:
            print(f"[WARN] Batch book fetch failed: {exc}")

    for i, book in enumerate(books, start=1):
        token_id = str(book.get("asset_id") or "")
        if not token_id:
            continue

        ask = best_ask_from_book(book)
        bid = best_bid_from_book(book)
        book_state[token_id] = {"best_ask": ask, "best_bid": bid}

        if i <= 5:
            info = token_map.get(token_id, {})
            print(f"[INFO] Seed {info.get('fighter', token_id[:12])}: bid={format_price(bid)} ask={format_price(ask)}")

        maybe_alert(
            token_id,
            ask,
            bid,
            token_map,
            threshold,
            alerted_asset_ids,
            no_notify,
            title,
            sports_states,
            resolved_asset_ids,
            require_sports_live,
            unsafe_ignore_live_gate,
        )


def build_alert_message(info: dict, ask_price: float, bid_price: Optional[float], threshold: float) -> str:
    opponent = info.get("opponent")
    opponent_line = f"Opponent: {opponent}" if opponent else f"Fight: {info.get('fight_label', 'UFC moneyline')}"
    favorite_price = 1 - ask_price

    return "\n".join(
        [
            "UFC 99/1 live odds alert",
            f"Event: {info.get('event_title', 'UFC event')}",
            f"Fighter: {info.get('fighter', 'Unknown')}",
            opponent_line,
            f"Buy ask: {format_price(ask_price)} ({format_percent(ask_price)})",
            f"Implied other side: {format_percent(favorite_price)}",
            f"Best bid: {format_price(bid_price)}",
            f"Trigger: ask <= {format_price(threshold)}",
            "Notification only. No bet placed.",
        ]
    )


def log_alert(info: dict, ask_price: float, bid_price: Optional[float]) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, "alerts.log")
    line = (
        f"{datetime.now().isoformat()} | {info.get('event_slug')} | {info.get('fighter')} | "
        f"ask={format_price(ask_price)} | bid={format_price(bid_price)}"
    )
    with open(path, "a") as f:
        f.write(line + "\n")


def maybe_alert(
    token_id: str,
    ask_price: Optional[float],
    bid_price: Optional[float],
    token_map: dict,
    threshold: float,
    alerted_asset_ids: set,
    no_notify: bool,
    title: str,
    sports_states: dict,
    resolved_asset_ids: set,
    require_sports_live: bool,
    unsafe_ignore_live_gate: bool,
) -> None:
    if not should_alert(token_id, ask_price, threshold, alerted_asset_ids):
        return

    info = token_map.get(token_id, {})
    allowed, reason = is_live_alert_allowed(
        token_id,
        info,
        sports_states,
        resolved_asset_ids,
        require_sports_live=require_sports_live,
        unsafe_ignore_live_gate=unsafe_ignore_live_gate,
    )
    if not allowed:
        print(f"[INFO] Alert suppressed for {info.get('fighter', token_id[:12])}: {reason}")
        return

    alerted_asset_ids.add(token_id)
    message = build_alert_message(info, ask_price, bid_price, threshold)
    print()
    print("=" * 60)
    print("[ALERT]")
    print(message)
    print("=" * 60)
    print()
    log_alert(info, ask_price, bid_price)
    send_pushover(message, info.get("event_url"), title, no_notify)


def subscribe_assets(wsapp, token_ids: list[str], chunk_size: int = 500) -> None:
    for i in range(0, len(token_ids), chunk_size):
        chunk = token_ids[i : i + chunk_size]
        wsapp.send(
            json.dumps(
                {
                    "type": "market",
                    "assets_ids": chunk,
                    "custom_feature_enabled": True,
                }
            )
        )
    print(f"[INFO] Subscribed to {len(token_ids)} asset IDs")


def start_sports_state_worker(
    sports_states: dict,
    tokens_by_slug: dict,
    book_state: dict,
    token_map: dict,
    threshold: float,
    alerted_asset_ids: set,
    no_notify: bool,
    title: str,
    resolved_asset_ids: set,
    require_sports_live: bool,
    unsafe_ignore_live_gate: bool,
) -> None:
    def evaluate_slug(slug: str) -> None:
        for token_id in tokens_by_slug.get(slug, []):
            state = book_state.get(token_id) or {}
            maybe_alert(
                token_id,
                state.get("best_ask"),
                state.get("best_bid"),
                token_map,
                threshold,
                alerted_asset_ids,
                no_notify,
                title,
                sports_states,
                resolved_asset_ids,
                require_sports_live,
                unsafe_ignore_live_gate,
            )

    def on_open(wsapp):
        print(f"[INFO] Connected to {SPORTS_WS_URL}")

    def on_message(wsapp, message):
        if message == "ping":
            wsapp.send("pong")
            return

        try:
            data = json.loads(message)
        except (TypeError, JSONDecodeError):
            return

        state = sports_state_from_message(data)
        if not state:
            return

        slug = state["slug"]
        if slug not in tokens_by_slug:
            return

        sports_states[slug] = state
        status = state.get("status") or ("live" if state.get("live") else "ended" if state.get("ended") else "unknown")
        print(f"[INFO] Sports state: {slug} status={status} live={state.get('live')} ended={state.get('ended')}")

        if state.get("live") and not state.get("ended"):
            evaluate_slug(slug)

    def on_error(wsapp, error):
        print(f"[WARN] Sports WebSocket error: {error}")

    def on_close(wsapp, close_status_code, close_msg):
        print(f"[WARN] Sports WebSocket closed (code={close_status_code}, msg={close_msg})")

    def run():
        while True:
            wsapp = websocket.WebSocketApp(
                SPORTS_WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            wsapp.run_forever()
            time.sleep(5)

    threading.Thread(target=run, daemon=True).start()


def run_monitor(args) -> None:
    threshold = float(os.environ.get("UFC_LIVE_ALERT_PRICE") or DEFAULT_ALERT_PRICE)
    title = os.environ.get("UFC_LIVE_ALERT_TITLE") or "UFC 99/1 Live Odds"
    heartbeat_seconds = int(os.environ.get("UFC_LIVE_HEARTBEAT_SECONDS") or DEFAULT_HEARTBEAT_SECONDS)
    unsafe_ignore_live_gate = bool(args.unsafe_ignore_live_gate)
    require_sports_live = env_bool("UFC_REQUIRE_SPORTS_LIVE", DEFAULT_REQUIRE_SPORTS_LIVE) and not unsafe_ignore_live_gate

    events = find_event_by_slug_or_search(args.target)
    token_map, token_ids = build_token_map(events)
    tokens_by_slug = group_tokens_by_slug(token_map)

    if args.list:
        for event in events:
            print(f"{event.get('slug')} | {event.get('title')}")
        print(f"\nFound {len(events)} UFC events and {len(token_ids)} moneyline tokens")
        return

    if not token_ids:
        print("[ERROR] No UFC moneyline tokens found")
        sys.exit(1)

    print("=" * 60)
    print("UFC Live 99/1 Odds Monitor")
    print("=" * 60)
    print(f"[INFO] Target: {args.target}")
    print(f"[INFO] Events: {len(events)}")
    print(f"[INFO] Moneyline tokens: {len(token_ids)}")
    print(f"[INFO] Alert threshold: ask <= {format_price(threshold)}")
    print(f"[INFO] Notifications: {'disabled' if args.no_notify else 'enabled'}")
    print(f"[INFO] Live gate: {'sports websocket required' if require_sports_live else 'not required'}")
    if unsafe_ignore_live_gate:
        print("[WARN] Unsafe live gate bypass enabled")
    print()

    book_state = {}
    alerted_asset_ids = set()
    sports_states = {}
    resolved_asset_ids = set()

    if require_sports_live:
        start_sports_state_worker(
            sports_states,
            tokens_by_slug,
            book_state,
            token_map,
            threshold,
            alerted_asset_ids,
            args.no_notify,
            title,
            resolved_asset_ids,
            require_sports_live,
            unsafe_ignore_live_gate,
        )

    seed_books(
        token_ids,
        book_state,
        token_map,
        threshold,
        alerted_asset_ids,
        args.no_notify,
        title,
        sports_states,
        resolved_asset_ids,
        require_sports_live,
        unsafe_ignore_live_gate,
    )

    if args.seed_only:
        return

    started_at = time.time()
    last_heartbeat = time.time()

    def on_open(wsapp):
        print(f"[INFO] Connected to {WS_URL}")
        subscribe_assets(wsapp, token_ids)
        if args.max_seconds:
            def close_after_timeout():
                time.sleep(args.max_seconds)
                print("[INFO] Max seconds reached, closing WebSocket")
                wsapp.close()

            threading.Thread(target=close_after_timeout, daemon=True).start()

    def on_message(wsapp, message):
        nonlocal last_heartbeat

        if args.max_seconds and time.time() - started_at >= args.max_seconds:
            print("[INFO] Max seconds reached, closing WebSocket")
            wsapp.close()
            return

        if isinstance(message, bytes):
            message = message.decode("utf-8", errors="ignore")
        message = (message or "").strip()
        if not message or message.upper() in {"PING", "PONG"}:
            return

        try:
            payload = json.loads(message)
        except JSONDecodeError:
            return

        for data in payload if isinstance(payload, list) else [payload]:
            if not isinstance(data, dict):
                continue

            event_type = data.get("event_type")
            token_id = str(data.get("asset_id") or "")

            if event_type == "book":
                ask = best_ask_from_book(data)
                bid = best_bid_from_book(data)
            elif event_type == "best_bid_ask":
                ask = to_float(data.get("best_ask"))
                bid = to_float(data.get("best_bid"))
            elif event_type == "price_change":
                changes = data.get("price_changes") or []
                for change in changes:
                    asset_id = str(change.get("asset_id") or "")
                    ask = to_float(change.get("best_ask"))
                    bid = to_float(change.get("best_bid"))
                    if asset_id:
                        book_state[asset_id] = {"best_ask": ask, "best_bid": bid}
                        maybe_alert(
                            asset_id,
                            ask,
                            bid,
                            token_map,
                            threshold,
                            alerted_asset_ids,
                            args.no_notify,
                            title,
                            sports_states,
                            resolved_asset_ids,
                            require_sports_live,
                            unsafe_ignore_live_gate,
                        )
                continue
            elif event_type == "market_resolved":
                for asset_id in parse_json_list(data.get("assets_ids") or data.get("asset_ids")):
                    resolved_asset_ids.add(str(asset_id))
                print(f"[INFO] Market resolved: {data.get('slug') or data.get('market')}")
                continue
            else:
                continue

            if token_id:
                book_state[token_id] = {"best_ask": ask, "best_bid": bid}
                maybe_alert(
                    token_id,
                    ask,
                    bid,
                    token_map,
                    threshold,
                    alerted_asset_ids,
                    args.no_notify,
                    title,
                    sports_states,
                    resolved_asset_ids,
                    require_sports_live,
                    unsafe_ignore_live_gate,
                )

        if time.time() - last_heartbeat >= heartbeat_seconds:
            last_heartbeat = time.time()
            print(f"[INFO] Heartbeat: monitoring {len(token_ids)} tokens, alerts sent={len(alerted_asset_ids)}")

    def on_error(wsapp, error):
        print(f"[WARN] WebSocket error: {error}")

    def on_close(wsapp, close_status_code, close_msg):
        print(f"[INFO] WebSocket closed (code={close_status_code}, msg={close_msg})")

    while True:
        wsapp = websocket.WebSocketApp(
            WS_URL,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        wsapp.run_forever(ping_interval=30, ping_timeout=10)
        if args.max_seconds:
            break
        print("[INFO] Reconnecting in 5 seconds...")
        time.sleep(5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor live Polymarket UFC moneyline odds for 99/1 alerts")
    parser.add_argument("target", nargs="?", default="all", help="all, event slug, or fighter keyword search")
    parser.add_argument("--list", action="store_true", help="list matching UFC moneyline events and exit")
    parser.add_argument("--no-notify", action="store_true", help="print alerts without sending Pushover")
    parser.add_argument("--max-seconds", type=int, help="stop after this many seconds")
    parser.add_argument("--seed-only", action="store_true", help="fetch current books and exit without opening WebSocket")
    parser.add_argument(
        "--unsafe-ignore-live-gate",
        action="store_true",
        help="testing only: allow alerts without sports websocket live status",
    )
    args = parser.parse_args()

    run_monitor(args)


if __name__ == "__main__":
    main()
