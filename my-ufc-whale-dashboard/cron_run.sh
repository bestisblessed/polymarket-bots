#!/bin/bash

# Cron wrapper for hourly UFC whale dashboard update
# Runs the pipeline and pushes updated data to Streamlit repo

set -e

# Set safe PATH for cron environment (include pyenv for Raspberry Pi)
export PATH="$HOME/.pyenv/shims:$HOME/.pyenv/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Logging
LOG_FILE="$HOME/polymarket-bots/my-ufc-whale-dashboard/cron.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

{
  echo "[$TIMESTAMP] Starting hourly UFC whale dashboard update..."

  # Run the pipeline
  cd "$HOME/polymarket-bots/my-ufc-whale-dashboard"
  bash run.sh

  echo "[$TIMESTAMP] Pipeline completed. Checking for changes in Streamlit repo..."

  # Navigate to Streamlit repo and commit/push if changes exist
  cd "$HOME/mma-ai/Streamlit"

  # Check if there are any changes in data/whale_data
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
