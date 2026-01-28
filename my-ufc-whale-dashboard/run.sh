#!/bin/bash
# UFC Whale Dashboard - Fetch holders data for all UFC fights
# Cron: */30 * * * * /Users/td/Code/polymarket-bots/my-ufc-whale-dashboard/run.sh

cd "$(dirname "$0")"

LOG_DIR="$(pwd)/data/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_$(date +"%Y%m%d_%H%M%S").log"
exec > >(tee "$LOG_FILE")
exec 2> >(tee -a "$LOG_FILE" >&2)
echo "Logging to $LOG_FILE"

export PYTHONUNBUFFERED=1

python -u fetch_ufc_holders.py
