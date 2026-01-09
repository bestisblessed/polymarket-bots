#!/bin/bash
# Run the NFL large wager monitor
# Requires: PUSHOVER_API_TOKEN and PUSHOVER_GROUP_KEY in environment or .env file

cd "$(dirname "$0")"

# Load .env if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# -u for unbuffered output (important for logs)
python3 -u monitor_nfl_large_wagers.py
