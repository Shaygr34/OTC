#!/usr/bin/env python3
"""Clear all data from the ATM database. Use before first live run."""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "atm.db"

TABLES = [
    "candidates",
    "trades",
    "l2_snapshots",
    "trade_log",
    "alerts",
    "daily_scores",
]


def clear(db_path: Path = DB_PATH) -> None:
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    for table in TABLES:
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM sqlite_sequence")
    conn.commit()

    # Verify
    for table in TABLES:
        count = conn.execute(
            f"SELECT count(*) FROM {table}"
        ).fetchone()[0]
        print(f"  {table}: {count} rows")

    conn.close()
    print("All tables cleared.")


if __name__ == "__main__":
    clear()
