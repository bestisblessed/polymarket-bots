#!/usr/bin/env python3

import json
import os
from pathlib import Path
from typing import Any

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
BOT_DIR = SCRIPT_DIR.parent
REPO_DIR = BOT_DIR.parent

GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
DEFAULT_CLOB_HOST = "https://clob.polymarket.com"
DEFAULT_CHAIN_ID = 137


def load_env_files() -> list[Path]:
    loaded = []
    for path in (
        BOT_DIR / ".env.polymarket",
        BOT_DIR / ".env",
        REPO_DIR / ".env.polymarket",
        REPO_DIR / ".env",
    ):
        if path.exists():
            _load_env_file(path)
            loaded.append(path)
    return loaded


def _load_env_file(path: Path) -> None:
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def env_value(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value not in (None, ""):
            return value
    return default


def require_env(*names: str) -> str:
    value = env_value(*names)
    if value:
        return value
    joined = " or ".join(names)
    raise SystemExit(f"Missing required environment variable: {joined}")


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_int(value: str | None, default: int) -> int:
    if value in (None, ""):
        return default
    return int(str(value), 10)


def print_json(data: Any) -> None:
    print(json.dumps(to_plain(data), indent=2, sort_keys=True, default=str))


def to_plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_plain(item) for item in value]
    if hasattr(value, "model_dump"):
        return to_plain(value.model_dump())
    if hasattr(value, "__dict__"):
        return to_plain(value.__dict__)
    return str(value)


def fetch_json(url: str, params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def clob_get(path: str, params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    host = env_value("CLOB_HOST", "CLOB_API_URL", default=DEFAULT_CLOB_HOST).rstrip("/")
    return fetch_json(f"{host}/{path.lstrip('/')}", params=params, timeout=timeout)


def json_field(value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def market_tokens(market: dict[str, Any]) -> list[dict[str, str]]:
    outcomes = json_field(market.get("outcomes"), [])
    token_ids = json_field(market.get("clobTokenIds"), [])
    short_outcomes = json_field(market.get("shortOutcomes"), [])
    tokens = []
    for index, token_id in enumerate(token_ids or []):
        outcome = ""
        if index < len(short_outcomes or []):
            outcome = str(short_outcomes[index])
        elif index < len(outcomes or []):
            outcome = str(outcomes[index])
        tokens.append({"outcome": outcome or f"Outcome {index + 1}", "token_id": str(token_id)})
    return tokens


def market_summary(market: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": market.get("id"),
        "question": market.get("question") or market.get("title"),
        "slug": market.get("slug"),
        "condition_id": market.get("conditionId") or market.get("condition_id"),
        "active": market.get("active"),
        "closed": market.get("closed"),
        "accepting_orders": market.get("acceptingOrders"),
        "volume_24h": market.get("volume24hr") or market.get("volume24hrClob"),
        "liquidity": market.get("liquidity") or market.get("liquidityClob"),
        "tick_size": (
            market.get("minimum_tick_size")
            or market.get("minimumTickSize")
            or market.get("orderPriceMinTickSize")
        ),
        "neg_risk": market.get("negRisk") or market.get("neg_risk") or False,
        "tokens": market_tokens(market),
    }


def market_text(market: dict[str, Any]) -> str:
    searchable = [
        market.get("question"),
        market.get("title"),
        market.get("slug"),
        market.get("category"),
        market.get("description"),
    ]
    return " ".join(str(item).lower() for item in searchable if item)


def fetch_token_options(token_id: str, tick_size: str | None = None, neg_risk: bool | None = None) -> dict[str, Any]:
    options = {"tick_size": tick_size, "neg_risk": neg_risk}
    if options["tick_size"] is not None and options["neg_risk"] is not None:
        return options

    try:
        book = clob_get("book", {"token_id": token_id})
    except requests.RequestException:
        book = {}

    if options["tick_size"] is None:
        options["tick_size"] = str(book.get("tick_size") or book.get("tickSize") or "0.01")
    if options["neg_risk"] is None:
        options["neg_risk"] = parse_bool(book.get("neg_risk") or book.get("negRisk"), default=False)
    return options


def load_clob_sdk() -> dict[str, Any]:
    try:
        from py_clob_client_v2 import (  # type: ignore
            ApiCreds,
            ClobClient,
            MarketOrderArgs,
            OrderMarketCancelParams,
            OrderPayload,
            OrderArgs,
            OrderType,
            PartialCreateOrderOptions,
            Side,
        )
    except ImportError as exc:
        raise SystemExit(
            "Missing py-clob-client-v2. Install it with: python -m pip install -r requirements.txt"
        ) from exc

    sdk = {
        "ApiCreds": ApiCreds,
        "ClobClient": ClobClient,
        "MarketOrderArgs": MarketOrderArgs,
        "OrderMarketCancelParams": OrderMarketCancelParams,
        "OrderPayload": OrderPayload,
        "OrderArgs": OrderArgs,
        "OrderType": OrderType,
        "PartialCreateOrderOptions": PartialCreateOrderOptions,
        "Side": Side,
    }
    try:
        from py_clob_client_v2 import OpenOrderParams  # type: ignore

        sdk["OpenOrderParams"] = OpenOrderParams
    except ImportError:
        pass
    return sdk


def _signature_type_value(raw_value: str | None) -> Any:
    if raw_value in (None, ""):
        return None
    try:
        from py_clob_client_v2 import SignatureTypeV2  # type: ignore

        candidates = {
            "0": "EOA",
            "EOA": "EOA",
            "1": "POLY_PROXY",
            "POLY_PROXY": "POLY_PROXY",
            "2": "GNOSIS_SAFE",
            "GNOSIS_SAFE": "GNOSIS_SAFE",
            "3": "POLY_1271",
            "POLY_1271": "POLY_1271",
        }
        attr = candidates.get(str(raw_value).strip().upper())
        if attr and hasattr(SignatureTypeV2, attr):
            return getattr(SignatureTypeV2, attr)
    except ImportError:
        pass
    return int(raw_value) if str(raw_value).isdigit() else raw_value


def clob_client(require_creds: bool = False):
    load_env_files()
    sdk = load_clob_sdk()
    private_key = require_env("PRIVATE_KEY", "PK")
    host = env_value("CLOB_HOST", "CLOB_API_URL", default=DEFAULT_CLOB_HOST)
    chain_id = parse_int(env_value("POLYMARKET_CHAIN_ID", "CHAIN_ID"), DEFAULT_CHAIN_ID)
    kwargs: dict[str, Any] = {
        "host": host,
        "chain_id": chain_id,
        "key": private_key,
    }

    signature_type = _signature_type_value(env_value("POLYMARKET_SIGNATURE_TYPE", "SIGNATURE_TYPE"))
    if signature_type is not None:
        kwargs["signature_type"] = signature_type

    funder = env_value(
        "POLYMARKET_FUNDER",
        "FUNDER_ADDRESS",
        "DEPOSIT_WALLET_ADDRESS",
        "POLYMARKET_PROXY_ADDRESS",
    )
    if funder:
        kwargs["funder"] = funder

    if require_creds:
        kwargs["creds"] = api_creds(sdk["ApiCreds"])

    return sdk["ClobClient"](**kwargs)


def api_creds(ApiCreds):
    api_key = require_env("CLOB_API_KEY", "POLYMARKET_API_KEY")
    api_secret = require_env("CLOB_SECRET", "CLOB_API_SECRET", "POLYMARKET_API_SECRET")
    api_passphrase = require_env(
        "CLOB_PASS_PHRASE",
        "CLOB_API_PASSPHRASE",
        "CLOB_PASSPHRASE",
        "POLYMARKET_API_PASSPHRASE",
    )
    return ApiCreds(
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
    )


def enum_value(enum_cls, name: str):
    value = name.upper()
    if hasattr(enum_cls, value):
        return getattr(enum_cls, value)
    return value


def masked(value: str | None, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}...{value[-keep:]}"


def credential_fields(credentials: Any) -> dict[str, str]:
    plain = to_plain(credentials)
    if not isinstance(plain, dict):
        return {}
    return {
        "CLOB_API_KEY": str(plain.get("apiKey") or plain.get("api_key") or plain.get("key") or ""),
        "CLOB_SECRET": str(plain.get("secret") or plain.get("api_secret") or plain.get("apiSecret") or ""),
        "CLOB_PASS_PHRASE": str(
            plain.get("passphrase")
            or plain.get("api_passphrase")
            or plain.get("apiPassphrase")
            or ""
        ),
    }
