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

# Use explicit Python path for cron compatibility
# Resolves the actual binary path (handles pyenv shims, virtualenvs, etc.)
PYTHON=$(command -v python 2>/dev/null || command -v python3 2>/dev/null || echo "python")
if [ -x "$PYTHON" ]; then
  # Resolve symlinks to get the actual binary path
  PYTHON=$(readlink -f "$PYTHON" 2>/dev/null || realpath "$PYTHON" 2>/dev/null || echo "$PYTHON")
fi

# 1. Fetch live volume data for all active UFC markets
echo "Starting Volume Fetch..."
chmod +x get_market_current_holdings.sh
./get_market_current_holdings.sh

# 2. Fetch ticket counts
echo "Starting Ticket Count Fetch..."
"$PYTHON" -u utils/fetch_ufc_ticket_counts.py

# 3. Fetch holders data
echo "Starting Holders Fetch..."
"$PYTHON" -u utils/fetch_ufc_holders.py

# 4. After scraping, run the report on the latest CSV
LATEST_CSV=$(ls -t data/ufc_holders_*.csv 2>/dev/null | head -1)
if [ -n "$LATEST_CSV" ]; then
  echo "Running report on $LATEST_CSV"
  "$PYTHON" -u report_ufc_holders.py "$LATEST_CSV"
else
  echo "No CSV found to report on."
fi

# 5. Copy files to Dashboard
# Auto-detect path: use ~/mma-ai/Streamlit on Raspberry Pi, fallback to Mac path if it exists
if [ -d "$HOME/mma-ai/Streamlit/data/whale_data" ]; then
  DEST_DIR="$HOME/mma-ai/Streamlit/data/whale_data"
elif [ -d "/Users/td/Code/mma-ai/Streamlit/data/whale_data" ]; then
  DEST_DIR="/Users/td/Code/mma-ai/Streamlit/data/whale_data"
else
  echo "Warning: Streamlit data directory not found. Skipping copy."
  DEST_DIR=""
fi

if [ -n "$DEST_DIR" ]; then
  echo "Copying files to $DEST_DIR"
  mkdir -p "$DEST_DIR"
  
  # Copy PnL CSVs
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
fi

echo "Run complete."
