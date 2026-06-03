#!/bin/zsh
set -euo pipefail

export PATH="/Users/pablo/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SESSION_NAME="ufc-monitor"
EVENT_SLUG="${1:-all}"
LOG_FILE="$SCRIPT_DIR/logs/console.log"
PYTHON_BIN="/Users/pablo/.pyenv/shims/python"

cd "$SCRIPT_DIR"
mkdir -p logs

if ! command -v tmux >/dev/null 2>&1; then
  echo "ERROR: tmux not found"
  exit 1
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "ERROR: Python not found or not executable: $PYTHON_BIN"
  exit 1
fi

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "[INFO] UFC monitor already running in tmux session: $SESSION_NAME"
  exit 0
fi

echo "[INFO] Starting UFC monitor in tmux session: $SESSION_NAME"
echo "[INFO] Event slug: $EVENT_SLUG"
echo "[INFO] Log file: $LOG_FILE"
echo "[INFO] Python: $PYTHON_BIN"

tmux new-session -d -s "$SESSION_NAME" -c "$SCRIPT_DIR" "EVENT_SLUG='$EVENT_SLUG' LOG_FILE='$LOG_FILE' PYTHON_BIN='$PYTHON_BIN' exec /bin/zsh -lc 'while true; do echo \"[WATCHDOG] Starting monitor for \$EVENT_SLUG...\"; \"\$PYTHON_BIN\" monitor_ufc_large_wagers.py \"\$EVENT_SLUG\"; exit_code=\$?; echo \"[WATCHDOG] Monitor exited with code \$exit_code. Restarting in 10s...\"; sleep 10; done 2>&1 | tee -a \"\$LOG_FILE\"'"

tmux has-session -t "$SESSION_NAME"
echo "[INFO] UFC monitor started successfully"
