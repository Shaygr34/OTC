#!/usr/bin/env bash
# ATM Trading Engine - One-command setup
# Usage: bash setup.sh
set -euo pipefail

echo "=== ATM Trading Engine Setup ==="
echo ""

# Check Python version
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.12+ first."
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]); then
    echo "ERROR: Python 3.12+ required (found $PY_VERSION)"
    exit 1
fi
echo "[ok] Python $PY_VERSION"

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "[..] Creating virtual environment..."
    python3 -m venv .venv
    echo "[ok] Virtual environment created"
else
    echo "[ok] Virtual environment exists"
fi

# Install dependencies
echo "[..] Installing dependencies..."
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e ".[dev,dashboard]"
echo "[ok] Dependencies installed"

# Create .env from template if missing
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[ok] Created .env from template"
    echo "     >> Edit .env to configure IBKR connection and Telegram"
else
    echo "[ok] .env already exists"
fi

# Create data and log directories
mkdir -p data logs
echo "[ok] data/ and logs/ directories ready"

# Seed demo data so the dashboard has something to show
echo "[..] Seeding demo data..."
.venv/bin/python scripts/seed_realistic.py
echo "[ok] Demo data seeded"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Quick start:"
echo "  Mock mode:  bash start.sh"
echo "  Live IBKR:  bash start.sh --live"
echo ""
echo "Or run individually:"
echo "  Engine:     .venv/bin/python scripts/run_system.py"
echo "  Dashboard:  .venv/bin/python scripts/run_dashboard.py"
echo "  Tests:      .venv/bin/pytest tests/ -x -q"
echo ""
echo "Before going live with IBKR:"
echo "  1. Edit .env -> set ATM_USE_IBKR=1"
echo "  2. Edit config/watchlist.yaml -> add your tickers"
echo "  3. Make sure TWS/IB Gateway is running on port 7497"
