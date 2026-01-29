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

# After scraping, run the report on the latest CSV
LATEST_CSV=$(ls -t data/ufc_holders_*.csv 2>/dev/null | head -1)
if [ -n "$LATEST_CSV" ]; then
  echo "Running report on $LATEST_CSV"
  python -u report_ufc_holders.py "$LATEST_CSV"
else
  echo "No CSV found to report on."
fi
