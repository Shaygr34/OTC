#!/usr/bin/env python3
"""Launch the ATM Trading Engine Streamlit dashboard.

Usage:
    streamlit run scripts/run_dashboard.py          # Direct streamlit invocation
    python scripts/run_dashboard.py                 # Subprocess launcher
    python scripts/run_dashboard.py --port 8502
    python scripts/run_dashboard.py --db data/atm.db

When invoked via ``streamlit run``, this file delegates to src/dashboard/app.py.
When invoked via ``python``, it launches streamlit as a subprocess.
"""

import sys
from pathlib import Path

_APP_PATH = Path(__file__).resolve().parent.parent / "src" / "dashboard" / "app.py"


def _is_streamlit_runtime() -> bool:
    """Return True if we are running inside the Streamlit server."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


if _is_streamlit_runtime():
    # Streamlit is running this file — delegate to the real app module
    import importlib.util
    spec = importlib.util.spec_from_file_location("dashboard_app", str(_APP_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
else:
    # Running via ``python scripts/run_dashboard.py`` — launch streamlit
    def main():
        import argparse
        import subprocess

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
