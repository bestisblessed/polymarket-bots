#!/bin/bash
# */3 * * * * /home/trinity/polymarket-bots/my-openai-whale-bot/run.sh >> /home/trinity/polymarket-bots/my-openai-whale-bot/log_whales.log 2>&1

export PATH="$HOME/.pyenv/shims:$HOME/.pyenv/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
python monitor_whale_wallets.py