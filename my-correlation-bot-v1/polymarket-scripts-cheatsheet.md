# Polymarket Scripts Cheat Sheet

## Setup

```bash
python -m pip install -r my-correlation-bots/utils/requirements.txt
cp my-correlation-bots/.env.polymarket.example my-correlation-bots/.env.polymarket
cd my-correlation-bots/utils
```

## Scripts

- `poly_api_free_endpoints.py` - Prints the main free/public Polymarket API groups.
  `python poly_api_free_endpoints.py`
- `poly_search_markets.py` - Searches active markets and prints outcome token IDs.
  `python poly_search_markets.py --query "weather" --limit 10`
- `poly_clob_price.py` - Gets public CLOB midpoint, spread, BUY/SELL prices, and optional orderbook.
  `python poly_clob_price.py --token-id TOKEN_ID --book --depth 5`
- `poly_clob_derive_api_creds.py` - Derives CLOB API credentials from `PRIVATE_KEY`.
  `python poly_clob_derive_api_creds.py --show-secret`
- `poly_clob_limit_order.py` - Previews or submits a limit BUY/SELL order.
  `python poly_clob_limit_order.py --token-id TOKEN_ID --side BUY --price 0.45 --size 5`
- `poly_clob_market_order.py` - Previews or submits a FOK/FAK market-style order with worst-price protection.
  `python poly_clob_market_order.py --token-id TOKEN_ID --side BUY --amount 10 --worst-price 0.55 --type FOK`
- `poly_clob_orders.py` - Lists, gets, or cancels authenticated CLOB orders.
  `python poly_clob_orders.py list`
- `polymarket_template_utils.py` - Shared helper imported by the other scripts; do not run directly.

Order and cancel scripts are preview-only until you add `--live`.

## Exact `.env.polymarket` Values To Fill

```bash
PRIVATE_KEY=0xYOUR_PRIVATE_KEY
CLOB_API_KEY=your_clob_api_key
CLOB_SECRET=your_clob_secret
CLOB_PASS_PHRASE=your_clob_passphrase
CLOB_HOST=https://clob.polymarket.com
POLYMARKET_CHAIN_ID=137
POLYMARKET_SIGNATURE_TYPE=0
POLYMARKET_FUNDER=0xYOUR_WALLET_OR_DEPOSIT_WALLET_ADDRESS
```

- `PRIVATE_KEY` - Your wallet private key. Required to derive CLOB credentials and sign live orders.
- `CLOB_API_KEY` - Output from `poly_clob_derive_api_creds.py --show-secret`; required for authenticated CLOB calls.
- `CLOB_SECRET` - Output from credential derivation; required for authenticated CLOB calls.
- `CLOB_PASS_PHRASE` - Output from credential derivation; required for authenticated CLOB calls.
- `CLOB_HOST` - Polymarket production CLOB URL. Leave as `https://clob.polymarket.com`.
- `POLYMARKET_CHAIN_ID` - Polygon mainnet chain ID. Leave as `137`.
- `POLYMARKET_SIGNATURE_TYPE` - Account type: `0` EOA, `1` Polymarket proxy, `2` Gnosis Safe, `3` POLY_1271 deposit wallet.
- `POLYMARKET_FUNDER` - Wallet/proxy/deposit address that owns the funds used for trading. For a simple EOA, use your wallet address or omit this line.
