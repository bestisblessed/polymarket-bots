#!/bin/bash

if [ -z "$1" ]; then
  echo "Usage: ./get_event.sh <slug>"
  exit 1
fi

#curl -s "https://gamma-api.polymarket.com/events/slug/$1" | jq | tee "data/$1.json"
#curl -s "https://gamma-api.polymarket.com/events/slug/cfb-ore-ind-2026-01-09" | jq '.markets[0].clobTokenIds' | tee "data/$1.json"
curl -s "https://gamma-api.polymarket.com/events/slug/cfb-ore-ind-2026-01-09" | jq '.markets[0] | {outcomes, clobTokenIds}' | tee "data/$1.json"
