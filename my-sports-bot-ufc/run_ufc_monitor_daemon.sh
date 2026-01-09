#!/bin/bash
# UFC Whale Monitor Daemon Runner
#
# Starts/stops the UFC monitor in a detached screen/tmux session
# so it keeps running in the background even after you disconnect.
#
# Usage:
#   ./run_ufc_monitor_daemon.sh start <event_slug> [threshold_usd]
#   ./run_ufc_monitor_daemon.sh stop
#   ./run_ufc_monitor_daemon.sh status
#   ./run_ufc_monitor_daemon.sh logs
#   ./run_ufc_monitor_daemon.sh attach
#
# Examples:
#   ./run_ufc_monitor_daemon.sh start ufc-jus3-pad-2026-01-24
#   ./run_ufc_monitor_daemon.sh start ufc-jus3-pad-2026-01-24 10000
#   ./run_ufc_monitor_daemon.sh logs
#   ./run_ufc_monitor_daemon.sh attach
#   ./run_ufc_monitor_daemon.sh stop

set -e

sleep 30

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Session name for screen/tmux
SESSION_NAME="ufc-monitor"
LOG_DIR="logs"

# Check which session manager is available (prefer screen)
if command -v screen &> /dev/null; then
    SESSION_CMD="screen"
elif command -v tmux &> /dev/null; then
    SESSION_CMD="tmux"
else
    echo "ERROR: Neither 'screen' nor 'tmux' found. Please install one:"
    echo "  Ubuntu/Debian: sudo apt-get install screen"
    echo "  macOS: brew install screen"
    exit 1
fi

echo "[INFO] Using $SESSION_CMD for session management"

# ============================================================================
# COMMAND FUNCTIONS
# ============================================================================

start_monitor() {
    local event_slug="${1:-ufc-jus3-pad-2026-01-24}"
    local threshold="${2:-5000}"

    if [ -z "$event_slug" ]; then
        echo "ERROR: event_slug required"
        echo "Usage: $0 start <event_slug> [threshold_usd]"
        exit 1
    fi

    # Check if session already exists
    if check_session_exists; then
        echo "ERROR: Monitor already running in session '$SESSION_NAME'"
        echo "Run '$0 stop' to stop it first, or '$0 attach' to view it"
        exit 1
    fi

    mkdir -p "$LOG_DIR"

    echo "Starting UFC Whale Monitor..."
    echo "  Event: $event_slug"
    echo "  Threshold: \$$threshold"
    echo "  Session: $SESSION_NAME"
    echo ""

    export PYTHONUNBUFFERED=1

    if [ "$SESSION_CMD" = "screen" ]; then
        screen -dmS "$SESSION_NAME" bash -c "cd '$SCRIPT_DIR' && python3 monitor_ufc_large_wagers.py '$event_slug' --threshold '$threshold'"
    else  # tmux
        tmux new-session -d -s "$SESSION_NAME" -c "$SCRIPT_DIR" "python3 monitor_ufc_large_wagers.py '$event_slug' --threshold '$threshold'"
    fi

    sleep 1

    if check_session_exists; then
        echo "✓ Monitor started successfully!"
        echo ""
        echo "Commands:"
        echo "  View logs:       $0 logs"
        echo "  Attach console:  $0 attach"
        echo "  Stop monitor:    $0 stop"
        echo "  Check status:    $0 status"
    else
        echo "ERROR: Failed to start monitor"
        exit 1
    fi
}

stop_monitor() {
    if ! check_session_exists; then
        echo "Monitor is not running"
        exit 0
    fi

    echo "Stopping UFC Whale Monitor..."

    if [ "$SESSION_CMD" = "screen" ]; then
        screen -S "$SESSION_NAME" -X quit
    else  # tmux
        tmux kill-session -t "$SESSION_NAME"
    fi

    sleep 1

    if ! check_session_exists; then
        echo "✓ Monitor stopped successfully"
    else
        echo "ERROR: Failed to stop monitor"
        exit 1
    fi
}

attach_monitor() {
    if ! check_session_exists; then
        echo "ERROR: Monitor is not running"
        echo "Start it with: $0 start <event_slug>"
        exit 1
    fi

    echo "Attaching to monitor session (press Ctrl+A then D to detach in screen, or Ctrl+B then D in tmux)..."
    echo ""

    if [ "$SESSION_CMD" = "screen" ]; then
        screen -r "$SESSION_NAME"
    else  # tmux
        tmux attach-session -t "$SESSION_NAME"
    fi
}

show_logs() {
    if [ ! -d "$LOG_DIR" ]; then
        echo "No logs directory found"
        exit 1
    fi

    # Find the most recent log file
    log_file=$(ls -t "$LOG_DIR"/ufc_*.log 2>/dev/null | head -1)

    if [ -z "$log_file" ]; then
        echo "No log files found in $LOG_DIR"
        exit 1
    fi

    echo "Viewing logs from: $log_file"
    echo "Press Ctrl+C to stop (or use 'tail -f' for live streaming)"
    echo ""
    tail -f "$log_file"
}

check_status() {
    if check_session_exists; then
        echo "✓ Monitor is RUNNING (session: $SESSION_NAME)"
        echo ""

        if [ "$SESSION_CMD" = "screen" ]; then
            echo "Active screen sessions:"
            screen -list | grep "$SESSION_NAME" || echo "  (not found in listing)"
        else  # tmux
            echo "Active tmux sessions:"
            tmux list-sessions | grep "$SESSION_NAME" || echo "  (not found in listing)"
        fi

        # Show latest log
        log_file=$(ls -t "$LOG_DIR"/ufc_*.log 2>/dev/null | head -1)
        if [ -n "$log_file" ]; then
            echo ""
            echo "Latest log entries:"
            tail -5 "$log_file"
        fi
    else
        echo "✗ Monitor is NOT running"
    fi
}

check_session_exists() {
    if [ "$SESSION_CMD" = "screen" ]; then
        screen -list | grep -q "^\s*[0-9]*\.$SESSION_NAME" && return 0 || return 1
    else  # tmux
        tmux list-sessions 2>/dev/null | grep -q "^$SESSION_NAME:" && return 0 || return 1
    fi
}

# ============================================================================
# MAIN
# ============================================================================

COMMAND="${1:-status}"

case "$COMMAND" in
    start)
        start_monitor "$2" "$3"
        ;;
    stop)
        stop_monitor
        ;;
    attach)
        attach_monitor
        ;;
    logs)
        show_logs
        ;;
    status)
        check_status
        ;;
    *)
        echo "UFC Whale Monitor Daemon"
        echo ""
        echo "Usage: $0 <command> [options]"
        echo ""
        echo "Commands:"
        echo "  start <event_slug> [threshold]  Start monitor in background"
        echo "  stop                            Stop the running monitor"
        echo "  attach                          Attach to running monitor console"
        echo "  logs                            View live logs from monitor"
        echo "  status                          Check if monitor is running"
        echo ""
        echo "Examples:"
        echo "  $0 start ufc-jus3-pad-2026-01-24"
        echo "  $0 start ufc-jus3-pad-2026-01-24 10000"
        echo "  $0 status"
        echo "  $0 logs"
        echo "  $0 attach"
        echo "  $0 stop"
        exit 1
        ;;
esac
