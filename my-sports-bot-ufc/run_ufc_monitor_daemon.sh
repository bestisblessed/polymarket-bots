#!/bin/bash
# UFC Whale Monitor Daemon Runner
#
# Starts/stops the UFC monitor in a detached screen/tmux session
# so it keeps running in the background even after you disconnect.
#
# Usage:
#   ./run_ufc_monitor_daemon.sh start [all|<event_slug>]
#   ./run_ufc_monitor_daemon.sh restart [all|<event_slug>]
#   ./run_ufc_monitor_daemon.sh stop
#   ./run_ufc_monitor_daemon.sh status
#   ./run_ufc_monitor_daemon.sh logs
#   ./run_ufc_monitor_daemon.sh attach
#
# Examples:
#   ./run_ufc_monitor_daemon.sh start
#   ./run_ufc_monitor_daemon.sh start all
#   ./run_ufc_monitor_daemon.sh start ufc-jus3-pad-2026-01-24
#   ./run_ufc_monitor_daemon.sh restart all
#   ./run_ufc_monitor_daemon.sh logs
#   ./run_ufc_monitor_daemon.sh attach
#   ./run_ufc_monitor_daemon.sh stop

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Session name for screen/tmux
SESSION_NAME="ufc-monitor"
LOG_DIR="logs"
STARTUP_NETWORK_WAIT_SECONDS="${STARTUP_NETWORK_WAIT_SECONDS:-30}"
RESTART_NETWORK_WAIT_SECONDS="${RESTART_NETWORK_WAIT_SECONDS:-10}"

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
    local event_slug="${1:-all}"

    if [ -n "$2" ]; then
        echo "[WARN] Threshold arg ignored; set THRESHOLD in .env"
    fi

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

    if [ "$STARTUP_NETWORK_WAIT_SECONDS" -gt 0 ]; then
        echo "[INFO] Waiting ${STARTUP_NETWORK_WAIT_SECONDS}s for network readiness before start..."
        sleep "$STARTUP_NETWORK_WAIT_SECONDS"
    fi

    mkdir -p "$LOG_DIR"

    echo "Starting UFC Whale Monitor..."
    echo "  Event: $event_slug"
    echo "  Threshold: (from .env THRESHOLD)"
    echo "  Session: $SESSION_NAME"
    echo ""

    export PYTHONUNBUFFERED=1

    # Watchdog wrapper: auto-restarts the Python process if it exits (crash, OOM, etc.)
    # Output is timestamped on screen; only important lines + 1 heartbeat/min go to console.log
    CONSOLE_LOG="$SCRIPT_DIR/logs/console.log"
    WATCHDOG_CMD="cd '$SCRIPT_DIR' && mkdir -p logs && while true; do echo '[WATCHDOG] Starting monitor...'; python3 monitor_ufc_large_wagers.py '$event_slug'; EXIT_CODE=\$?; echo \"[WATCHDOG] Monitor exited (code=\$EXIT_CODE). Restarting in 10s...\"; sleep 10; done 2>&1 | awk -v logfile='$CONSOLE_LOG' 'BEGIN{last=0} { ts=strftime(\"[%Y-%m-%d %H:%M:%S]\"); print ts, \$0; fflush(); if (\$0 ~ /ALERT|ERROR|WARN|WATCHDOG|Heartbeat|Health check/) { print ts, \$0 >> logfile; fflush(logfile) } else { now=systime(); if (now-last>=60) { print ts, \$0 >> logfile; fflush(logfile); last=now } } }'"

    if [ "$SESSION_CMD" = "screen" ]; then
        screen -dmS "$SESSION_NAME" bash -c "$WATCHDOG_CMD"
    else  # tmux
        tmux new-session -d -s "$SESSION_NAME" -c "$SCRIPT_DIR" "bash -c \"$WATCHDOG_CMD\""
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

restart_monitor() {
    local event_slug="${1:-all}"

    if check_session_exists; then
        echo "Killing existing UFC Whale Monitor session..."

        if [ "$SESSION_CMD" = "screen" ]; then
            screen -S "$SESSION_NAME" -X quit
        else  # tmux
            tmux kill-session -t "$SESSION_NAME"
        fi

        sleep 1

        if check_session_exists; then
            echo "ERROR: Failed to kill existing monitor session"
            exit 1
        fi
    else
        echo "[INFO] Monitor is not running; starting a new session"
    fi

    STARTUP_NETWORK_WAIT_SECONDS="$RESTART_NETWORK_WAIT_SECONDS"
    start_monitor "$event_slug" "$2"
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
    restart)
        restart_monitor "$2" "$3"
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
        echo "  start <event_slug>              Start monitor in background"
        echo "  restart <event_slug>            Kill existing session and start monitor"
        echo "  stop                            Stop the running monitor"
        echo "  attach                          Attach to running monitor console"
        echo "  logs                            View live logs from monitor"
        echo "  status                          Check if monitor is running"
        echo ""
        echo "Examples:"
        echo "  $0 start ufc-jus3-pad-2026-01-24"
        echo "  $0 restart all"
        echo "  $0 status"
        echo "  $0 logs"
        echo "  $0 attach"
        echo "  $0 stop"
        exit 1
        ;;
esac
