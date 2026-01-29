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

# 1. Fetch live volume data for all active UFC markets
echo "Starting Volume Fetch..."
chmod +x get_market_current_holdings.sh
./get_market_current_holdings.sh

# 2. Fetch ticket counts
echo "Starting Ticket Count Fetch..."
python -u utils/fetch_ufc_ticket_counts.py

# 3. Fetch holders data
echo "Starting Holders Fetch..."
python -u utils/fetch_ufc_holders.py

# 4. After scraping, run the report on the latest CSV
LATEST_CSV=$(ls -t data/ufc_holders_*.csv 2>/dev/null | head -1)
if [ -n "$LATEST_CSV" ]; then
  echo "Running report on $LATEST_CSV"
  python -u report_ufc_holders.py "$LATEST_CSV"
else
  echo "No CSV found to report on."
fi

# 5. Copy files to Dashboard
DEST_DIR="/Users/td/Code/mma-ai/Streamlit/data/whale_data/"
echo "Copying files to $DEST_DIR"

# Copy PnL CSVs
# Using simple cp as in original script, but suppressing error if no match found just in case
cp data/ufc_holders_*_pnl.csv "$DEST_DIR" 2>/dev/null || echo "No PnL CSVs found to copy."

# Copy Volume Data
if [ -f "data/all_ufc_volumes.json" ]; then
    cp "data/all_ufc_volumes.json" "$DEST_DIR"
    echo "Copied volume data."
else
    echo "Warning: data/all_ufc_volumes.json not found."
fi

# Copy Ticket Count Data
if [ -f "data/all_ufc_ticket_counts.json" ]; then
    cp "data/all_ufc_ticket_counts.json" "$DEST_DIR"
    echo "Copied ticket count data."
else
    echo "Warning: data/all_ufc_ticket_counts.json not found."
fi

echo "Run complete."
