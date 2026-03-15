#!/usr/bin/env bash
# ATM Trading Engine - Start engine + dashboard
# Usage:
#   bash start.sh          # Mock mode (no TWS needed)
#   bash start.sh --live   # IBKR live mode (TWS must be running)
set -euo pipefail

# Check setup
if [ ! -d ".venv" ]; then
    echo "Run 'bash setup.sh' first."
    exit 1
fi

LIVE_MODE=0
for arg in "$@"; do
    case $arg in
        --live) LIVE_MODE=1 ;;
    esac
done

# Export IBKR flag
if [ "$LIVE_MODE" -eq 1 ]; then
    export ATM_USE_IBKR=1
    echo "=== ATM Engine [LIVE - IBKR] ==="
else
    export ATM_USE_IBKR=0
    echo "=== ATM Engine [MOCK] ==="
fi

# Cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down..."
    kill "$ENGINE_PID" 2>/dev/null || true
    kill "$DASH_PID" 2>/dev/null || true
    wait 2>/dev/null
    echo "Done."
}
trap cleanup EXIT INT TERM

# Start engine in background
echo "Starting engine..."
.venv/bin/python scripts/run_system.py &
ENGINE_PID=$!

# Give engine a moment to initialize DB
sleep 2

# Start dashboard
echo "Starting dashboard on http://localhost:8501"
.venv/bin/python scripts/run_dashboard.py --port 8501 &
DASH_PID=$!

echo ""
echo "Running. Press Ctrl+C to stop."
echo "  Dashboard: http://localhost:8501"
echo ""

# Wait for either process to exit
wait -n "$ENGINE_PID" "$DASH_PID" 2>/dev/null || true
