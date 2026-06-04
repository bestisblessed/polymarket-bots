#!/bin/bash

# Cron wrapper for hourly UFC whale dashboard update
# Runs the pipeline and pushes updated data to the Streamlit repo.

set -e

export PATH="/Users/pablo/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

SCRIPT_DIR="/Users/pablo/Code/polymarket-bots/my-ufc-whale-dashboard"
STREAMLIT_DIR="/Users/pablo/Code/mma-ai/Streamlit"
LOG_FILE="$SCRIPT_DIR/cron.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

{
  echo "[$TIMESTAMP] Starting hourly UFC whale dashboard update..."

  cd "$SCRIPT_DIR"
  bash run.sh

  echo "[$TIMESTAMP] Pipeline completed. Checking for changes in Streamlit repo..."

  cd "$STREAMLIT_DIR"
  git pull

  if git status --porcelain | grep -q "data/whale_data"; then
    echo "[$TIMESTAMP] Changes detected in data/whale_data. Committing and pushing..."
    git add data/whale_data/
    git commit -m "Update whale data ($(date '+%Y-%m-%d %H:%M:%S'))"
    git push origin main
    echo "[$TIMESTAMP] Successfully pushed to main branch."
  else
    echo "[$TIMESTAMP] No changes in data/whale_data. Skipping commit."
  fi

  echo "[$TIMESTAMP] Hourly update completed successfully."

} >> "$LOG_FILE" 2>&1
