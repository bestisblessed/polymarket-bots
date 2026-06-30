# Polymarket API Script Templates

Simple Python scripts for free Polymarket API reads and basic authenticated CLOB order workflows.

The zip contains:

- `poly_api_free_endpoints.py`: prints the main public/free API groups.
- `poly_search_markets.py`: searches active markets and prints outcome token IDs.
- `poly_clob_price.py`: gets CLOB price, midpoint, spread, and orderbook data.
- `poly_clob_derive_api_creds.py`: derives CLOB API credentials from your private key.
- `poly_clob_limit_order.py`: previews or submits limit BUY/SELL orders.
- `poly_clob_market_order.py`: previews or submits market-style BUY/SELL orders.
- `poly_clob_orders.py`: lists, gets, and cancels your open orders.
- `polymarket_template_utils.py`: shared helper used by the scripts.
- `.env.polymarket.example`: local credential template.
- `requirements.txt`: minimal Python dependencies for this utility folder.

## 1. Install

From the repo root:

```bash
python -m pip install -r my-correlation-bots/utils/requirements.txt
```

Copy the env template:

```bash
cp my-correlation-bots/.env.polymarket.example my-correlation-bots/.env.polymarket
```

Fill in `PRIVATE_KEY`. If your Polymarket funds are in a proxy/deposit wallet, also set:

```bash
POLYMARKET_SIGNATURE_TYPE=1
POLYMARKET_FUNDER=0xYourProxyOrDepositWallet
```

Signature types:

- `0`: EOA wallet.
- `1`: Polymarket proxy wallet.
- `2`: Gnosis Safe.
- `3`: POLY_1271 deposit wallet.

## 2. Public API Examples

Print the free API map:

```bash
python my-correlation-bots/utils/poly_api_free_endpoints.py
```

Search active markets:

```bash
python my-correlation-bots/utils/poly_search_markets.py --query "weather" --limit 10
```

Get machine-readable market search output:

```bash
python my-correlation-bots/utils/poly_search_markets.py --query "sports" --limit 5 --json
```

Get CLOB price data for a token:

```bash
python my-correlation-bots/utils/poly_clob_price.py --token-id TOKEN_ID
```

Get CLOB price plus orderbook:

```bash
python my-correlation-bots/utils/poly_clob_price.py --token-id TOKEN_ID --book --depth 5
```

## 3. Account Setup

Derive your CLOB API credentials:

```bash
python my-correlation-bots/utils/poly_clob_derive_api_creds.py --show-secret
```

Paste the printed values into `my-correlation-bots/.env.polymarket`:

```bash
CLOB_API_KEY=...
CLOB_SECRET=...
CLOB_PASS_PHRASE=...
```

Check open orders:

```bash
python my-correlation-bots/utils/poly_clob_orders.py list
```

Get one order:

```bash
python my-correlation-bots/utils/poly_clob_orders.py get --order-id ORDER_ID
```

## 4. Order Examples

All order and cancel commands are preview-only unless you add `--live`.

Preview a limit buy:

```bash
python my-correlation-bots/utils/poly_clob_limit_order.py --token-id TOKEN_ID --side BUY --price 0.45 --size 5
```

Submit a limit buy:

```bash
python my-correlation-bots/utils/poly_clob_limit_order.py --token-id TOKEN_ID --side BUY --price 0.45 --size 5 --live
```

Preview a limit sell:

```bash
python my-correlation-bots/utils/poly_clob_limit_order.py --token-id TOKEN_ID --side SELL --price 0.60 --size 5
```

Submit a market-style buy. For `BUY`, `--amount` is USDC/pUSD spend:

```bash
python my-correlation-bots/utils/poly_clob_market_order.py --token-id TOKEN_ID --side BUY --amount 10 --worst-price 0.55 --type FOK --live
```

Submit a market-style sell. For `SELL`, `--amount` is shares:

```bash
python my-correlation-bots/utils/poly_clob_market_order.py --token-id TOKEN_ID --side SELL --amount 5 --worst-price 0.45 --type FAK --live
```

Preview canceling one order:

```bash
python my-correlation-bots/utils/poly_clob_orders.py cancel --order-id ORDER_ID
```

Actually cancel one order:

```bash
python my-correlation-bots/utils/poly_clob_orders.py cancel --order-id ORDER_ID --live
```

Preview canceling all open orders:

```bash
python my-correlation-bots/utils/poly_clob_orders.py cancel-all
```

Actually cancel all open orders:

```bash
python my-correlation-bots/utils/poly_clob_orders.py cancel-all --live
```

## 5. Safety Notes

- Public market search and price/orderbook scripts do not need credentials.
- Credential, order listing, live order, and live cancel commands require `PRIVATE_KEY` and CLOB API credentials.
- Preview mode does not submit or cancel orders.
- Never commit `my-correlation-bots/.env.polymarket`.
- Official docs: https://docs.polymarket.com/
