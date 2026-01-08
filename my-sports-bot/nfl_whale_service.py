"""
Unified NFL whale monitor service (single process).

Runs:
- Real-time pending order monitoring via Polymarket CLOB WebSocket (reuses monitor_pending_orders.py)
- Periodic polling for executed trades (reuses get_nfl_game_bets.py)
- Periodic polling for holder snapshots + profit snapshots (reuses monitor_game_holders*.py)

Why: operational simplicity. You run ONE systemd service instead of multiple cron entries.

Official API bases (docs):
- CLOB WebSocket: wss://ws-subscriptions-clob.polymarket.com/ws/
- Data API: https://data-api.polymarket.com
- Gamma API: https://gamma-api.polymarket.com
See: https://docs.polymarket.com/quickstart/reference/endpoints
"""

import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class ServiceConfig:
    trades_interval_s: int
    holders_interval_s: int
    profit_interval_s: int


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[config] Invalid int for {name}={raw!r}, using default={default}")
        return default


def load_config() -> ServiceConfig:
    # Defaults tuned to “frequent enough” without hammering endpoints
    return ServiceConfig(
        trades_interval_s=_env_int("NFL_TRADES_INTERVAL_S", 180),
        holders_interval_s=_env_int("NFL_HOLDERS_INTERVAL_S", 300),
        profit_interval_s=_env_int("NFL_PROFIT_INTERVAL_S", 480),
    )


def run_forever_poll_loop(
    *,
    name: str,
    interval_s: int,
    lock: threading.Lock,
    fn: Callable[[], None],
    stop_event: threading.Event,
) -> None:
    """Run fn() forever on an interval, serializing execution across polling loops."""
    next_run = 0.0
    backoff_s = 1.0
    while not stop_event.is_set():
        now = time.time()
        if now < next_run:
            stop_event.wait(timeout=min(1.0, next_run - now))
            continue

        acquired = lock.acquire(timeout=30)
        if not acquired:
            print(f"[{name}] Skipping run: could not acquire shared poll lock")
            next_run = time.time() + interval_s
            continue

        try:
            start = time.time()
            print(f"[{name}] Starting")
            fn()
            dur = time.time() - start
            print(f"[{name}] Done in {dur:.2f}s")
            backoff_s = 1.0
            next_run = time.time() + interval_s
        except Exception as e:
            # Basic backoff to avoid tight crash loops
            print(f"[{name}] Error: {type(e).__name__}: {e}")
            next_run = time.time() + min(interval_s, max(5.0, backoff_s))
            backoff_s = min(300.0, backoff_s * 2.0)
        finally:
            lock.release()


def start_ws_thread(stop_event: threading.Event) -> threading.Thread:
    # Import inside to avoid side effects at module import time
    import monitor_pending_orders

    def _run_ws() -> None:
        # WS loop is independent; it reconnects internally
        try:
            monitor_pending_orders.connect_websocket()
        except Exception as e:
            # If WS thread crashes, let systemd restart the service
            print(f"[ws] Fatal error: {type(e).__name__}: {e}")
            stop_event.set()
            raise

    t = threading.Thread(target=_run_ws, name="ws_orderbook", daemon=True)
    t.start()
    return t


def make_trades_runner() -> Callable[[], None]:
    import get_nfl_game_bets

    def _run() -> None:
        # Reuse existing batch mode + notification logic
        get_nfl_game_bets.collect_for_all_markets(send_notifications=True)

    return _run


def make_holders_runner() -> Callable[[], None]:
    import monitor_game_holders

    def _run() -> None:
        monitor_game_holders.main()

    return _run


def make_profit_runner() -> Callable[[], None]:
    import monitor_game_holders_profit

    def _run() -> None:
        monitor_game_holders_profit.main()

    return _run


def main(argv: Optional[list[str]] = None) -> int:
    load_dotenv()
    cfg = load_config()

    print("=" * 72)
    print("Unified NFL Whale Monitor Service")
    print("=" * 72)
    print(f"- Trades poll interval:  {cfg.trades_interval_s}s")
    print(f"- Holders poll interval: {cfg.holders_interval_s}s")
    print(f"- Profit poll interval:  {cfg.profit_interval_s}s")
    print("=" * 72)
    print()

    stop_event = threading.Event()
    poll_lock = threading.Lock()

    # Start WS realtime monitor
    start_ws_thread(stop_event)

    # Start polling loops
    threads = [
        threading.Thread(
            target=run_forever_poll_loop,
            name="poll_trades",
            daemon=True,
            kwargs={
                "name": "trades",
                "interval_s": cfg.trades_interval_s,
                "lock": poll_lock,
                "fn": make_trades_runner(),
                "stop_event": stop_event,
            },
        ),
        threading.Thread(
            target=run_forever_poll_loop,
            name="poll_holders",
            daemon=True,
            kwargs={
                "name": "holders",
                "interval_s": cfg.holders_interval_s,
                "lock": poll_lock,
                "fn": make_holders_runner(),
                "stop_event": stop_event,
            },
        ),
        threading.Thread(
            target=run_forever_poll_loop,
            name="poll_profit",
            daemon=True,
            kwargs={
                "name": "profit",
                "interval_s": cfg.profit_interval_s,
                "lock": poll_lock,
                "fn": make_profit_runner(),
                "stop_event": stop_event,
            },
        ),
    ]
    for t in threads:
        t.start()

    # Wait forever; systemd handles restarts.
    try:
        while not stop_event.is_set():
            time.sleep(1)
        return 1
    except KeyboardInterrupt:
        print("\nShutting down...")
        stop_event.set()
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

