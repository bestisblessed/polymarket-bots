#!/bin/bash
# */3 * * * * /home/trinity/polymarket-bots/my-sports-bot/run_monitor_game_holders_profit.sh >> /home/trinity/polymarket-bots/my-sports-bot/log_whales_profit.log 2>&1

export PATH="$HOME/.pyenv/shims:$HOME/.pyenv/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
python monitor_game_holders_profit.py
