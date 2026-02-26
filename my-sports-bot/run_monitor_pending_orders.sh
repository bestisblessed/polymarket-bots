#!/bin/bash
# */3 * * * * /home/trinity/polymarket-bots/my-sports-bot/run_monitor_pending_orders.sh >> /home/trinity/polymarket-bots/my-sports-bot/log_pending_orders.log 2>&1

export PATH="$HOME/.pyenv/shims:$HOME/.pyenv/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
python monitor_pending_orders.py