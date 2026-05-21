#!/bin/bash
# Live UFC 99/1 odds monitor runner.
#
# Usage:
#   ./run.sh [all|<event_slug>|<fighter keywords>]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ "$#" -eq 0 ]; then
  set -- all
fi

TARGET="$1"
if [[ "$TARGET" == --* ]]; then
  TARGET="all"
fi

echo "Starting UFC Live 99/1 Odds Monitor..."
echo "Target: $TARGET"
echo "Alert price: ${UFC_LIVE_ALERT_PRICE:-from .env or default 0.01}"
echo ""

export PYTHONUNBUFFERED=1
python monitor_live_ufc_odds.py "$@"
