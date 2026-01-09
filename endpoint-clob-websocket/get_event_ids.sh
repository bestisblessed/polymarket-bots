#!/bin/bash
# Sources (Polymarket Gamma API):
# - https://docs.polymarket.com/developers/gamma-markets-api/overview
# - https://docs.polymarket.com/developers/gamma-markets-api/fetch-markets-guide

set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "Usage: ./get_event_ids.sh <slug>" >&2
  exit 1
fi

slug="$1"

curl -s "https://gamma-api.polymarket.com/events/slug/${slug}" \
  | jq '.markets[] | select(.sportsMarketType == "moneyline") | {outcomes, clobTokenIds}' \
  | tee "data/${slug}.json"
