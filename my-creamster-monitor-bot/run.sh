#!/bin/bash
# Cron: 6-59/8 * * * * /home/trinity/polymarket-bots/my-creamster-monitor-bot/run.sh >> /home/trinity/polymarket-bots/my-creamster-monitor-bot/log.log 2>&1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
python monitor_creamster_wallet.py
