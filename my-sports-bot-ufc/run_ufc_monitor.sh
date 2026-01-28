#!/bin/bash
# UFC Whale Monitor Runner
#
# Usage:
#   ./run_ufc_monitor.sh <event_slug>
#
# Examples:
#   ./run_ufc_monitor.sh ufc-jus3-pad-2026-01-24

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

EVENT_SLUG="${1:-ufc-jus3-pad-2026-01-24}"

if [ -n "$2" ]; then
  echo "[WARN] Threshold arg ignored; set THRESHOLD in .env"
fi

echo "Starting UFC Whale Monitor..."
echo "Event: $EVENT_SLUG"
echo "Threshold: (from .env THRESHOLD)"
echo ""

export PYTHONUNBUFFERED=1
python3 monitor_ufc_large_wagers.py "$EVENT_SLUG"
