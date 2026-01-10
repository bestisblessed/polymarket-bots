#!/bin/bash
# UFC Open Order Monitor Runner
#
# Usage:
#   ./run_ufc_open_orders.sh <event_slug> [threshold_usd]
#
# Examples:
#   ./run_ufc_open_orders.sh ufc-jus3-pad-2026-01-24
#   ./run_ufc_open_orders.sh ufc-jus3-pad-2026-01-24 10000

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

EVENT_SLUG="${1:-ufc-jus3-pad-2026-01-24}"
THRESHOLD="${2:-5000}"

echo "Starting UFC Open Order Monitor..."
echo "Event: $EVENT_SLUG"
echo "Threshold: \$$THRESHOLD"
echo ""

export PYTHONUNBUFFERED=1
python3 monitor_ufc_open_orders.py "$EVENT_SLUG" --threshold "$THRESHOLD"
