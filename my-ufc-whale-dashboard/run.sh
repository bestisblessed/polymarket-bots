#!/bin/bash
set -e

# UFC Whale Dashboard - Fetch holders data for all UFC fights
# Cron: 40 * * * * /Users/pablo/Code/polymarket-bots/my-ufc-whale-dashboard/cron_run.sh

cd "$(dirname "$0")"

LOG_DIR="$(pwd)/data/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_$(date +"%Y%m%d_%H%M%S").log"
exec > >(tee "$LOG_FILE")
exec 2> >(tee -a "$LOG_FILE" >&2)
echo "Logging to $LOG_FILE"

export PYTHONUNBUFFERED=1

# Use explicit Python path for cron compatibility.
PYTHON="/Users/pablo/.pyenv/shims/python"

# 1. Fetch live volume data for all active UFC markets
echo "Starting Volume Fetch..."
chmod +x get_market_current_holdings.sh
./get_market_current_holdings.sh

# 2. Fetch ticket counts
echo "Starting Ticket Count Fetch..."
"$PYTHON" -u utils/fetch_ufc_ticket_counts.py

# 3. Fetch holders data
echo "Starting Holders Fetch..."
RUN_MARKER=$(mktemp data/.run_marker.XXXXXX)
trap 'rm -f "$RUN_MARKER"' EXIT
"$PYTHON" -u utils/fetch_ufc_holders.py

# 4. After scraping, run the report on the latest CSV
LATEST_CSV=$(find data -maxdepth 1 -type f -name "ufc_holders_*.csv" ! -name "*_pnl.csv" -newer "$RUN_MARKER" | sort | tail -1)
LATEST_PNL_CSV=""
if [ -n "$LATEST_CSV" ]; then
  echo "Running report on $LATEST_CSV"
  "$PYTHON" -u report_ufc_holders.py "$LATEST_CSV"
  LATEST_PNL_CSV="${LATEST_CSV%.csv}_pnl.csv"
else
  echo "No CSV found to report on."
fi

# 5. Merge this run into the compact Streamlit runtime.
# Auto-detect path: use the Mac path first, then Raspberry Pi path if present.
if [ -d "/Users/pablo/Code/mma-ai/Streamlit" ]; then
  STREAMLIT_DIR="/Users/pablo/Code/mma-ai/Streamlit"
elif [ -d "$HOME/mma-ai/Streamlit" ]; then
  STREAMLIT_DIR="$HOME/mma-ai/Streamlit"
elif [ -d "/Users/td/Code/mma-ai/Streamlit" ]; then
  STREAMLIT_DIR="/Users/td/Code/mma-ai/Streamlit"
else
  echo "Error: Streamlit directory not found."
  exit 1
fi

UPDATE_SCRIPT="$STREAMLIT_DIR/scripts/update_whale_runtime.py"
RUNTIME_DIR="$STREAMLIT_DIR/data/whale_data"
VOLUMES_JSON="data/all_ufc_volumes.json"
TICKETS_JSON="data/all_ufc_ticket_counts.json"

for required_file in "$LATEST_PNL_CSV" "$VOLUMES_JSON" "$TICKETS_JSON" "$UPDATE_SCRIPT"; do
  if [ ! -f "$required_file" ]; then
    echo "Error: required compact-runtime input not found: $required_file"
    exit 1
  fi
done

echo "Updating compact Streamlit whale runtime in $RUNTIME_DIR"
"$PYTHON" -u "$UPDATE_SCRIPT" update \
  --snapshot "$LATEST_PNL_CSV" \
  --volumes "$VOLUMES_JSON" \
  --tickets "$TICKETS_JSON" \
  --runtime-dir "$RUNTIME_DIR"

echo "Run complete."
