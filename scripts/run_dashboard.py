#!/usr/bin/env python3
"""Launch the ATM Trading Engine Streamlit dashboard.

Usage:
    python scripts/run_dashboard.py
    python scripts/run_dashboard.py --port 8502
    python scripts/run_dashboard.py --db data/atm.db
"""

import argparse
import subprocess
import sys
from pathlib import Path

_APP_PATH = Path(__file__).resolve().parent.parent / "src" / "dashboard" / "app.py"


def main():
    parser = argparse.ArgumentParser(description="ATM Dashboard")
    parser.add_argument("--port", type=int, default=8501, help="Streamlit port")
    parser.add_argument("--db", type=str, default=None, help="SQLite database path")
    args = parser.parse_args()

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(_APP_PATH),
        "--server.port", str(args.port),
        "--server.headless", "true",
    ]

    if args.db:
        cmd.extend(["--", f"--db={args.db}"])

    print(f"Starting dashboard on http://localhost:{args.port}")
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
