#!/usr/bin/env python3
"""
Calculate a Polymarket user's prediction and PnL success rates.

Prediction result is based on the held outcome's current/final token price.
PnL result is based on realizedPnl for closed positions and cashPnl for current positions.
"""

import argparse
import re
import sys
from urllib.parse import urlparse

import requests


DATA_API_BASE = "https://data-api.polymarket.com"
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
CLOSED_POSITIONS_LIMIT = 50
CURRENT_POSITIONS_LIMIT = 500
WIN_PRICE_THRESHOLD = 0.98
LOSS_PRICE_THRESHOLD = 0.02


def normalize_user_target(raw_target):
    """Return ("wallet"|"username", normalized_value) for CLI input."""
    target = raw_target.strip()
    if not target:
        raise ValueError("User target cannot be empty")

    if target.startswith("http://") or target.startswith("https://"):
        parsed = urlparse(target)
        host = parsed.netloc.lower()
        if not host.endswith("polymarket.com"):
            raise ValueError(f"Unsupported profile URL host: {parsed.netloc}")
        path = parsed.path.strip("/")
        if not path.startswith("@"):
            raise ValueError("Polymarket profile URLs must look like https://polymarket.com/@username")
        target = path

    if WALLET_RE.match(target):
        return "wallet", target.lower()

    if target.startswith("@"):
        target = target[1:]

    target = target.strip()
    if not target:
        raise ValueError("Username cannot be empty")
    if not USERNAME_RE.match(target):
        raise ValueError(f"Invalid username: {target}")

    return "username", target.lower()


def select_exact_profile_match(username, profiles):
    """Select the one exact case-insensitive username match from search results."""
    wanted = username.lower()
    matches = []

    for profile in profiles:
        profile_names = [
            str(profile.get("name") or ""),
            str(profile.get("username") or ""),
        ]
        if any(profile_name.lower() == wanted for profile_name in profile_names):
            matches.append(profile)

    if not matches:
        raise ValueError(f"No exact Polymarket profile match found for @{username}")
    if len(matches) > 1:
        raise ValueError(f"Multiple exact Polymarket profile matches found for @{username}")

    wallet = matches[0].get("proxyWallet")
    if not wallet or not WALLET_RE.match(wallet):
        raise ValueError(f"Profile @{username} did not include a valid proxy wallet")

    matches[0]["proxyWallet"] = wallet.lower()
    return matches[0]


def realized_pnl(position):
    """Return realizedPnl as a float, treating missing or blank values as 0."""
    value = position.get("realizedPnl", 0)
    if value in (None, ""):
        return 0.0
    return float(value)


def numeric_field(position, field_name, default=None):
    value = position.get(field_name, default)
    if value in (None, ""):
        return default
    return float(value)


def classify_prediction_result(position):
    """Classify whether the held outcome ultimately hit based on its token price."""
    cur_price = numeric_field(position, "curPrice")
    if cur_price is None:
        return "pending"
    if cur_price >= WIN_PRICE_THRESHOLD:
        return "success"
    if cur_price <= LOSS_PRICE_THRESHOLD:
        return "failure"
    return "pending"


def classify_pnl_result(pnl_value):
    if pnl_value > 0:
        return "profit"
    if pnl_value < 0:
        return "loss"
    return "breakeven"


def position_market_key(position, fallback_index):
    """Return the market-level key used by /traded, preferring conditionId."""
    for field_name in ("conditionId", "slug"):
        value = position.get(field_name)
        if value:
            return str(value)

    title = position.get("title")
    if title:
        return f"{title}|{position.get('eventSlug', '')}"

    return f"row-{fallback_index}"


def terminal_rank(position):
    result = classify_prediction_result(position)
    if result == "success":
        return 2
    if result == "failure":
        return 1
    return 0


def select_market_representative(rows):
    """Pick one row to represent a market when Data API returns duplicate rows."""
    closed_rows = [row for row in rows if row["_source"] == "closed"]
    if closed_rows:
        profitable_closed_rows = [row for row in closed_rows if realized_pnl(row) > 0]
        candidates = profitable_closed_rows or closed_rows
        selected = max(
            candidates,
            key=lambda row: (
                terminal_rank(row),
                realized_pnl(row),
                numeric_field(row, "curPrice", 0.0),
            ),
        )
    else:
        selected = max(
            rows,
            key=lambda row: (
                terminal_rank(row),
                abs(numeric_field(row, "cashPnl", 0.0)),
                numeric_field(row, "currentValue", 0.0),
            ),
        )

    result = dict(selected)
    result["_source_row_count"] = len(rows)
    result["_source_kinds"] = ",".join(sorted({row["_source"] for row in rows}))
    return result


def reconcile_market_rows(current_positions, closed_positions):
    """Collapse raw position rows to one representative row per market."""
    grouped = {}
    fallback_index = 0

    for source, positions in (("current", current_positions), ("closed", closed_positions)):
        for position in positions:
            fallback_index += 1
            row = dict(position)
            row["_source"] = source
            key = position_market_key(row, fallback_index)
            row["_market_key"] = key
            grouped.setdefault(key, []).append(row)

    return [select_market_representative(rows) for rows in grouped.values()]


def calculate_success_summary(total_traded, closed_positions, current_positions=None):
    current_positions = current_positions or []
    market_rows = reconcile_market_rows(current_positions, closed_positions)
    closed_market_rows = [row for row in market_rows if row["_source"] == "closed"]
    current_market_rows = [row for row in market_rows if row["_source"] == "current"]

    prediction_successes = 0
    prediction_failures = 0
    prediction_pending = 0

    for position in market_rows:
        result = classify_prediction_result(position)
        if result == "success":
            prediction_successes += 1
        elif result == "failure":
            prediction_failures += 1
        else:
            prediction_pending += 1

    raw_closed_count = len(closed_positions)
    raw_current_count = len(current_positions)
    raw_source_row_count = raw_current_count + raw_closed_count
    closed_count = len(closed_market_rows)
    current_count = len(current_market_rows)
    source_row_count = current_count + closed_count
    duplicate_market_rows = raw_source_row_count - source_row_count
    prediction_resolved_count = prediction_successes + prediction_failures
    prediction_hit_rate = None
    if prediction_resolved_count:
        prediction_hit_rate = prediction_successes / prediction_resolved_count * 100

    profitable_closed_trades = 0
    negative_pnl_closed_trades = 0
    breakeven_closed_trades = 0
    for position in closed_market_rows:
        pnl_result = classify_pnl_result(realized_pnl(position))
        if pnl_result == "profit":
            profitable_closed_trades += 1
        elif pnl_result == "loss":
            negative_pnl_closed_trades += 1
        else:
            breakeven_closed_trades += 1

    closed_pnl_rate = None
    if closed_count:
        closed_pnl_rate = profitable_closed_trades / closed_count * 100

    profile_visible_closed_wins = profitable_closed_trades
    profile_visible_closed_losses = 0
    profile_visible_closed_count = profile_visible_closed_wins + profile_visible_closed_losses
    profile_visible_closed_hit_rate = None
    if profile_visible_closed_count:
        profile_visible_closed_hit_rate = profile_visible_closed_wins / profile_visible_closed_count * 100

    api_only_closed_markets = closed_count - profile_visible_closed_count

    active_unresolved = 0
    active_current_profit = 0
    active_current_loss = 0
    active_current_breakeven = 0
    for position in current_market_rows:
        if classify_prediction_result(position) == "pending":
            active_unresolved += 1

        pnl_result = classify_pnl_result(numeric_field(position, "cashPnl", 0.0))
        if pnl_result == "profit":
            active_current_profit += 1
        elif pnl_result == "loss":
            active_current_loss += 1
        else:
            active_current_breakeven += 1

    source_row_share = None
    if total_traded:
        source_row_share = source_row_count / int(total_traded) * 100

    return {
        "total_traded": int(total_traded),
        "raw_current_count": raw_current_count,
        "raw_closed_count": raw_closed_count,
        "raw_source_row_count": raw_source_row_count,
        "current_count": current_count,
        "closed_count": closed_count,
        "source_row_count": source_row_count,
        "duplicate_market_rows": duplicate_market_rows,
        "website_visible_wins": profitable_closed_trades,
        "prediction_successes": prediction_successes,
        "prediction_failures": prediction_failures,
        "prediction_pending": prediction_pending,
        "prediction_resolved_count": prediction_resolved_count,
        "prediction_hit_rate": prediction_hit_rate,
        "api_final_outcome_hits": prediction_successes,
        "api_final_outcome_misses": prediction_failures,
        "api_final_outcome_pending": prediction_pending,
        "api_final_outcome_resolved_count": prediction_resolved_count,
        "api_final_outcome_hit_rate": prediction_hit_rate,
        "profile_visible_closed_wins": profile_visible_closed_wins,
        "profile_visible_closed_losses": profile_visible_closed_losses,
        "profile_visible_closed_count": profile_visible_closed_count,
        "profile_visible_closed_hit_rate": profile_visible_closed_hit_rate,
        "api_only_closed_markets": api_only_closed_markets,
        "profitable_closed_trades": profitable_closed_trades,
        "negative_pnl_closed_trades": negative_pnl_closed_trades,
        "breakeven_closed_trades": breakeven_closed_trades,
        "closed_pnl_rate": closed_pnl_rate,
        "active_unresolved": active_unresolved,
        "active_current_profit": active_current_profit,
        "active_current_loss": active_current_loss,
        "active_current_breakeven": active_current_breakeven,
        "source_row_share": source_row_share,
    }


def request_json(session, url, params):
    response = session.get(url, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def resolve_username(session, username):
    data = request_json(
        session,
        f"{GAMMA_API_BASE}/public-search",
        {
            "q": username,
            "search_profiles": "true",
            "limit_per_type": 10,
        },
    )
    profiles = data.get("profiles") or []
    if not isinstance(profiles, list):
        raise ValueError("Unexpected /public-search response: profiles was not a list")
    return select_exact_profile_match(username, profiles)


def fetch_total_traded(session, wallet):
    data = request_json(session, f"{DATA_API_BASE}/traded", {"user": wallet})
    if "traded" not in data:
        raise ValueError("Unexpected /traded response: missing traded count")
    return int(data["traded"])


def fetch_current_positions(session, wallet):
    positions = []
    offset = 0

    while True:
        page = request_json(
            session,
            f"{DATA_API_BASE}/positions",
            {
                "user": wallet,
                "limit": CURRENT_POSITIONS_LIMIT,
                "offset": offset,
                "sizeThreshold": 0,
                "sortBy": "CURRENT",
                "sortDirection": "DESC",
            },
        )
        if not isinstance(page, list):
            raise ValueError("Unexpected /positions response: expected a list")

        positions.extend(page)
        if len(page) < CURRENT_POSITIONS_LIMIT:
            break

        offset += CURRENT_POSITIONS_LIMIT

    return positions


def fetch_closed_positions(session, wallet):
    positions = []
    offset = 0

    while True:
        page = request_json(
            session,
            f"{DATA_API_BASE}/closed-positions",
            {
                "user": wallet,
                "limit": CLOSED_POSITIONS_LIMIT,
                "offset": offset,
                "sortBy": "TIMESTAMP",
                "sortDirection": "DESC",
            },
        )
        if not isinstance(page, list):
            raise ValueError("Unexpected /closed-positions response: expected a list")

        positions.extend(page)
        if len(page) < CLOSED_POSITIONS_LIMIT:
            break

        offset += CLOSED_POSITIONS_LIMIT

    return positions


def format_money(value):
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def shorten(value, max_length):
    text = str(value or "")
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def result_label(position):
    result = classify_prediction_result(position)
    if result == "success":
        return "Hit"
    if result == "failure":
        return "Miss"
    return "Pending"


def pnl_value_for_row(position, source):
    if source == "current":
        return numeric_field(position, "cashPnl", 0.0)
    return realized_pnl(position)


def pnl_label(position, source):
    result = classify_pnl_result(pnl_value_for_row(position, source))
    if source == "current":
        return f"open {result}"
    return result


def visibility_label(position):
    if position["_source"] == "closed" and realized_pnl(position) <= 0:
        return "api-only"
    return "profile"


def print_summary(target_label, wallet, summary):
    print("Polymarket user prediction + PnL summary")
    if target_label:
        print(f"User: {target_label}")
    print(f"Wallet: {wallet}")
    print(
        "Prediction result: held outcome price >= "
        f"{WIN_PRICE_THRESHOLD:.2f} is a hit, <= {LOSS_PRICE_THRESHOLD:.2f} is a miss, otherwise pending."
    )
    print("PnL result: closed rows use realizedPnl; current rows use cashPnl.")
    print("")
    print(f"Total traded/predictions (/traded): {summary['total_traded']}")
    print(
        "Raw position rows fetched: "
        f"{summary['raw_current_count']} current + {summary['raw_closed_count']} closed = "
        f"{summary['raw_source_row_count']}"
    )
    print(f"Unique markets reconciled: {summary['source_row_count']}")
    if summary["duplicate_market_rows"]:
        print(f"Duplicate market rows collapsed: {summary['duplicate_market_rows']}")
    if summary["source_row_count"] != summary["total_traded"]:
        print(
            "Note: unique market count differs from /traded; inspect raw rows before treating this as a final rate."
        )
    print("")
    print("Profile Closed tab result:")
    print(f"  Visible closed wins: {summary['profile_visible_closed_wins']}")
    print(f"  Visible closed losses: {summary['profile_visible_closed_losses']}")
    if summary["profile_visible_closed_hit_rate"] is None:
        print("  Visible closed hit rate: N/A (0 visible closed rows)")
    else:
        print(
            f"  Visible closed hit rate: {summary['profile_visible_closed_hit_rate']:.2f}% "
            f"({summary['profile_visible_closed_wins']}/{summary['profile_visible_closed_count']})"
        )
    if summary["api_only_closed_markets"]:
        print(f"  API-only non-profitable closed markets: {summary['api_only_closed_markets']}")
    print("")
    print("API final-outcome audit:")
    print(f"  Hits: {summary['api_final_outcome_hits']}")
    print(f"  Misses: {summary['api_final_outcome_misses']}")
    print(f"  Pending/unresolved: {summary['api_final_outcome_pending']}")
    if summary["api_final_outcome_hit_rate"] is None:
        print("  Final-outcome hit rate: N/A (0 resolved prediction rows)")
    else:
        print(
            f"  Final-outcome hit rate: {summary['api_final_outcome_hit_rate']:.2f}% "
            f"({summary['api_final_outcome_hits']}/{summary['api_final_outcome_resolved_count']})"
        )
    print("")
    print("Closed PnL market audit:")
    print(f"  Profitable closed markets: {summary['profitable_closed_trades']}")
    print(f"  Negative PnL closed markets: {summary['negative_pnl_closed_trades']}")
    print(f"  Breakeven closed markets: {summary['breakeven_closed_trades']}")
    if summary["closed_pnl_rate"] is None:
        print("  Closed PnL success rate: N/A (0 closed markets)")
    else:
        print(
            f"  Closed PnL success rate: {summary['closed_pnl_rate']:.2f}% "
            f"({summary['profitable_closed_trades']}/{summary['closed_count']})"
        )
    print("")
    print("Current/open markets:")
    print(f"  Active unresolved markets: {summary['active_unresolved']}")
    print(f"  Current PnL profit/loss/breakeven: {summary['active_current_profit']}/"
          f"{summary['active_current_loss']}/{summary['active_current_breakeven']}")


def print_positions_table(current_positions, closed_positions):
    rows = reconcile_market_rows(current_positions, closed_positions)

    if not rows:
        print("")
        print("No positions returned.")
        return

    print("")
    print("Reconciled market rows")
    print(
        f"{'View':<9} {'Source':<8} {'Raw':>3} {'Predict':<8} {'PnL':<13} "
        f"{'Price':>7} {'PnL $':>14}  {'Outcome':<14} Title"
    )
    print("-" * 127)
    for position in rows:
        source = position["_source"]
        visibility = visibility_label(position)
        prediction = result_label(position)
        pnl_status = pnl_label(position, source)
        price = numeric_field(position, "curPrice", 0.0)
        pnl = format_money(pnl_value_for_row(position, source))
        raw_count = position.get("_source_row_count", 1)
        outcome = shorten(position.get("outcome", ""), 16)
        title = shorten(position.get("title", ""), 45)
        print(
            f"{visibility:<9} {source:<8} {raw_count:>3} {prediction:<8} {pnl_status:<13} "
            f"{price:>7.4f} {pnl:>14}  {outcome:<14} {title}"
        )


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Calculate profile-visible Closed-tab hit rate plus API outcome and PnL audits.",
    )
    parser.add_argument(
        "user",
        help="Polymarket wallet, username, @username, or profile URL",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])

    try:
        target_kind, target_value = normalize_user_target(args.user)
        session = requests.Session()
        session.headers.update({"User-Agent": "polymarket-bots-success-rate/1.0"})

        target_label = None
        if target_kind == "wallet":
            wallet = target_value
        else:
            profile = resolve_username(session, target_value)
            wallet = profile["proxyWallet"]
            target_label = profile.get("name") or profile.get("username") or target_value

        total_traded = fetch_total_traded(session, wallet)
        current_positions = fetch_current_positions(session, wallet)
        closed_positions = fetch_closed_positions(session, wallet)
        summary = calculate_success_summary(total_traded, closed_positions, current_positions)

        print_summary(target_label, wallet, summary)
        print_positions_table(current_positions, closed_positions)
        return 0
    except requests.HTTPError as exc:
        print(f"HTTP error from Polymarket API: {exc}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"Network error from Polymarket API: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
