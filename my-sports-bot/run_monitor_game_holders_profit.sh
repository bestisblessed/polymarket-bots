#!/bin/bash
# Cron (every 3 minutes):
# */3 * * * * cd /home/trinity/polymarket-bots/my-sports-bot && /usr/bin/python3 monitor_game_holders_profit.py >> data/monitor_game_holders_profit.log 2>&1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PYTHON="$(which python)"
"$PYTHON" monitor_game_holders_profit.py 2>&1 | tee -a log_whales_profit.log
