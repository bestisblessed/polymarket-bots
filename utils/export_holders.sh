#!/usr/bin/env bash
set -euo pipefail

# Export all current ERC-20 holders from a Blockscout v2 instance. The main
# CSV keeps externally owned wallets; the companion CSV audits exclusions.

readonly API_BASE="${BLOCKSCOUT_API_BASE:-https://robinhoodchain.blockscout.com/api/v2}"
readonly PAGE_SIZE="${BLOCKSCOUT_PAGE_SIZE:-50}"
readonly PAGE_DELAY_SECONDS="${BLOCKSCOUT_PAGE_DELAY_SECONDS:-0.25}"
readonly MAX_ATTEMPTS="${BLOCKSCOUT_MAX_ATTEMPTS:-8}"

usage() {
  cat <<'EOF'
Usage:
  ./export_holders.sh <token-contract-address> [output.csv]

Environment overrides:
  BLOCKSCOUT_API_BASE          Blockscout v2 API base URL
  BLOCKSCOUT_PAGE_DELAY_SECONDS Delay between successful page requests (default: 0.25)
  BLOCKSCOUT_MAX_ATTEMPTS      Attempts per request (default: 8)

The main CSV contains externally owned wallets. A companion
<output>.excluded.csv records contracts, pools, protocol addresses, and burn
addresses that were removed.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

command -v curl >/dev/null 2>&1 || die "curl is required"
command -v jq >/dev/null 2>&1 || die "jq is required"

[[ $# -ge 1 && $# -le 2 ]] || { usage >&2; exit 2; }
[[ "$1" == "-h" || "$1" == "--help" ]] && { usage; exit 0; }
TOKEN_ADDRESS="$1"
[[ "$TOKEN_ADDRESS" =~ ^0x[0-9A-Fa-f]{40}$ ]] || die "token address must be a 0x-prefixed 40-hex-character address"

TOKEN_LOWER="$(printf '%s' "$TOKEN_ADDRESS" | tr '[:upper:]' '[:lower:]')"
if [[ $# -eq 2 ]]; then
  OUTPUT="$2"
else
  OUTPUT="holders_${TOKEN_LOWER#0x}.csv"
fi
EXCLUDED_OUTPUT="${OUTPUT%.csv}.excluded.csv"

[[ "$PAGE_SIZE" =~ ^[1-9][0-9]*$ && "$PAGE_SIZE" -le 50 ]] || die "BLOCKSCOUT_PAGE_SIZE must be between 1 and 50"
[[ "$MAX_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || die "BLOCKSCOUT_MAX_ATTEMPTS must be a positive integer"

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/blockscout-holders.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
PAGE_JSON="$WORK_DIR/page.json"
PAGE_HEADERS="$WORK_DIR/headers.txt"
PAGE_ROWS="$WORK_DIR/rows.tsv"
ADDRESS_TMP="$WORK_DIR/addresses.txt"
MAIN_TMP="$WORK_DIR/main.csv"
EXCLUDED_TMP="$WORK_DIR/excluded.csv"

printf 'rank,wallet_address,balance_raw,balance_tokens,metadata\n' > "$MAIN_TMP"
printf 'rank,wallet_address,balance_raw,balance_tokens,exclusion_reason,metadata\n' > "$EXCLUDED_TMP"

fetch_json() {
  local url="$1"
  local expected="${2:-holders}"
  local attempt http_code retry_after sleep_for

  for ((attempt=1; attempt<=MAX_ATTEMPTS; attempt++)); do
    : > "$PAGE_HEADERS"
    http_code="$(curl --silent --show-error --location --fail-with-body \
      --connect-timeout 15 --max-time 90 \
      --dump-header "$PAGE_HEADERS" --output "$PAGE_JSON" \
      --write-out '%{http_code}' "$url" 2>"$WORK_DIR/curl.err" || true)"

    if [[ "$http_code" =~ ^2[0-9][0-9]$ ]] && {
      if [[ "$expected" == "token" ]]; then
        jq -e 'type == "object" and (.name? or .symbol? or .holders_count?)' "$PAGE_JSON" >/dev/null 2>&1
      else
        jq -e '.items | type == "array"' "$PAGE_JSON" >/dev/null 2>&1
      fi
    }; then
      return 0
    fi

    if [[ "$http_code" == "429" || "$http_code" =~ ^5[0-9][0-9]$ || -z "$http_code" ]]; then
      retry_after="$(awk 'tolower($1)=="retry-after:" {gsub(/\r/,"",$2); print $2; exit}' "$PAGE_HEADERS")"
      if [[ "$retry_after" =~ ^[0-9]+$ ]]; then
        sleep_for="$retry_after"
      else
        sleep_for=$((attempt * attempt * 2))
        (( sleep_for > 60 )) && sleep_for=60
      fi
      printf 'Retrying request (%d/%d) after %ss; HTTP status: %s\n' "$attempt" "$MAX_ATTEMPTS" "$sleep_for" "${http_code:-unknown}" >&2
      sleep "$sleep_for"
      continue
    fi

    printf '%s\n' "$(cat "$PAGE_JSON" 2>/dev/null || cat "$WORK_DIR/curl.err")" >&2
    die "Blockscout request failed with HTTP status ${http_code:-unknown}: $url"
  done

  die "Blockscout request failed after $MAX_ATTEMPTS attempts: $url"
}

TOKEN_INFO_URL="$API_BASE/tokens/$TOKEN_ADDRESS"
fetch_json "$TOKEN_INFO_URL" token
TOKEN_NAME="$(jq -r '.name // "unknown"' "$PAGE_JSON")"
TOKEN_SYMBOL="$(jq -r '.symbol // "unknown"' "$PAGE_JSON")"
EXPECTED_HOLDERS="$(jq -r '.holders_count // "unknown"' "$PAGE_JSON")"

printf 'Token: %s (%s)\n' "$TOKEN_NAME" "$TOKEN_SYMBOL"
printf 'Expected indexed holders: %s\n' "$EXPECTED_HOLDERS"

NEXT_URL="$API_BASE/tokens/$TOKEN_ADDRESS/holders?items_count=$PAGE_SIZE"
PAGE_NUMBER=0
RAW_COUNT=0
INCLUDED_COUNT=0
EXCLUDED_COUNT=0
UNIQUE_COUNT=0

while [[ -n "$NEXT_URL" ]]; do
  PAGE_NUMBER=$((PAGE_NUMBER + 1))
  fetch_json "$NEXT_URL"
  jq -r --argjson rank_start "$RAW_COUNT" '
    def decimal18:
      tostring as $s |
      ($s | length) as $n |
      if $n <= 18 then
        ("0." + (("000000000000000000" | .[0:(18 - $n)]) + $s))
      else
        (($s[0:($n - 18)]) + "." + $s[($n - 18):])
      end
      | sub("0+$"; "")
      | sub("\\.$"; "");
    def metadata_text:
      [(.address.name // empty),
       (.address.public_tags[]? | .display_name? // empty),
       (.address.public_tags[]? | .label? // empty),
       (.address.private_tags[]? | .display_name? // empty),
       (.address.private_tags[]? | .label? // empty),
       (.address.watchlist_names[]? | .display_name? // empty),
       (.address.watchlist_names[]? | .label? // empty)]
      | map(select(. != null) | tostring)
      | unique
      | join(" | ");
    def is_dead:
      (.address.hash | ascii_downcase) as $a
      | ($a == "0x0000000000000000000000000000000000000000"
         or $a == "0x000000000000000000000000000000000000dead"
         or $a == "0x0000000000000000000000000000000000000001");
    .items
    | to_entries[]
    | .value as $item
    | ($item | metadata_text) as $metadata
    | (if ($item.address.is_contract // false) then "contract"
       elif ($item | is_dead) then "burn_or_system_address"
       elif ($metadata | test("pool|router|factory|manager|adapter|bridge|locker|staking|treasury"; "i")) then "protocol_metadata"
       else "" end) as $reason
    | ([(($rank_start + .key + 1)), $item.address.hash, $item.value, ($item.value | decimal18)] | @csv) as $base
    | if $reason == "" then ("included\t" + $base + "," + ([$metadata] | @csv))
      else ("excluded\t" + $base + "," + ([$reason] | @csv) + "," + ([$metadata] | @csv)) end
  ' "$PAGE_JSON" > "$PAGE_ROWS"

  PAGE_COUNT="$(jq '.items | length' "$PAGE_JSON")"
  while IFS=$'\t' read -r kind csv_line; do
    [[ -n "$kind" ]] || continue
    address="$(printf '%s\n' "$csv_line" | awk -F, '{gsub(/"/,"",$2); print tolower($2)}')"
    printf '%s\n' "$address" >> "$ADDRESS_TMP"
    UNIQUE_COUNT=$((UNIQUE_COUNT + 1))
    if [[ "$kind" == "included" ]]; then
      printf '%s\n' "$csv_line" >> "$MAIN_TMP"
      INCLUDED_COUNT=$((INCLUDED_COUNT + 1))
    else
      printf '%s\n' "$csv_line" >> "$EXCLUDED_TMP"
      EXCLUDED_COUNT=$((EXCLUDED_COUNT + 1))
    fi
  done < "$PAGE_ROWS"

  RAW_COUNT=$((RAW_COUNT + PAGE_COUNT))
  printf 'Page %d: %d holders; processed %d; included %d; excluded %d\n' \
    "$PAGE_NUMBER" "$PAGE_COUNT" "$RAW_COUNT" "$INCLUDED_COUNT" "$EXCLUDED_COUNT"

  NEXT_PARAMS="$(jq -r '.next_page_params // empty | to_entries | map(.key + "=" + (.value | tostring)) | join("&")' "$PAGE_JSON")"
  if [[ -n "$NEXT_PARAMS" ]]; then
    NEXT_URL="$API_BASE/tokens/$TOKEN_ADDRESS/holders?$NEXT_PARAMS"
    sleep "$PAGE_DELAY_SECONDS"
  else
    NEXT_URL=""
  fi
done

UNIQUE_COUNT="$(sort -u "$ADDRESS_TMP" | wc -l | tr -d ' ')"
[[ "$RAW_COUNT" -eq "$UNIQUE_COUNT" ]] || die "processed $RAW_COUNT rows but found $UNIQUE_COUNT unique addresses"
if [[ "$EXPECTED_HOLDERS" =~ ^[0-9]+$ && "$RAW_COUNT" -ne "$EXPECTED_HOLDERS" ]]; then
  die "pagination completed at $RAW_COUNT holders, but token metadata reported $EXPECTED_HOLDERS"
fi

mkdir -p "$(dirname "$OUTPUT")" "$(dirname "$EXCLUDED_OUTPUT")"
mv "$MAIN_TMP" "$OUTPUT"
mv "$EXCLUDED_TMP" "$EXCLUDED_OUTPUT"

printf '\nComplete.\n'
printf 'Raw holders processed: %d\n' "$RAW_COUNT"
printf 'Wallet rows written: %d -> %s\n' "$INCLUDED_COUNT" "$OUTPUT"
printf 'Excluded rows written: %d -> %s\n' "$EXCLUDED_COUNT" "$EXCLUDED_OUTPUT"
printf 'Verified: no duplicate addresses, pagination ended normally, and holder count matched token metadata.\n'
