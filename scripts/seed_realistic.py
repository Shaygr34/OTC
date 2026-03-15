"""Seed data/atm.db with realistic mock data for dashboard development.

Creates 20 candidates across all price tiers, with multi-day scores,
L2 snapshots, trades, and alerts — enough to experience the full dashboard
without needing IBKR connected.

Usage:
    .venv/bin/python scripts/seed_realistic.py
"""

import json
import random
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "atm.db"

# ── Candidate definitions ─────────────────────────────────────

CANDIDATES = [
    # (ticker, price_tier, base_price, base_score, status)
    # TRIP_ZERO tier ($0.0001-$0.0005)
    ("ZZXQ", "TRIP_ZERO", "0.0001", 88, "active"),
    ("PPVV", "TRIP_ZERO", "0.0002", 74, "active"),
    ("MMRL", "TRIP_ZERO", "0.0001", 42, "active"),
    # TRIPS tier ($0.0001-$0.0009)
    ("ABCD", "TRIPS", "0.0003", 92, "active"),
    ("EFGH", "TRIPS", "0.0005", 85, "active"),
    ("IJKL", "TRIPS", "0.0007", 76, "active"),
    ("QRST", "TRIPS", "0.0004", 63, "active"),
    ("WXYZ", "TRIPS", "0.0006", 55, "rejected"),
    # LOW_DUBS tier ($0.001-$0.003)
    ("LDUB", "LOW_DUBS", "0.0015", 83, "active"),
    ("NKTR", "LOW_DUBS", "0.0022", 71, "active"),
    ("FRZN", "LOW_DUBS", "0.0028", 48, "active"),
    # DUBS tier ($0.001-$0.0099)
    ("DUBX", "DUBS", "0.0045", 90, "active"),
    ("GRPH", "DUBS", "0.0068", 78, "active"),
    ("MVST", "DUBS", "0.0091", 66, "active"),
    ("RVLT", "DUBS", "0.0055", 39, "rejected"),
    # PENNIES tier ($0.01-$0.03)
    ("PNYX", "PENNIES", "0.012", 87, "active"),
    ("SLVR", "PENNIES", "0.021", 81, "active"),
    ("CPRX", "PENNIES", "0.018", 72, "active"),
    ("BRST", "PENNIES", "0.025", 58, "active"),
    ("DMPD", "PENNIES", "0.015", 35, "rejected"),
]

# Market makers
GOOD_MMS = ["ETRF", "CSTI", "GTSM", "NITE"]
NEUTRAL_MMS = ["OTCN", "OTCX", "CDEL", "INTL", "VIRT"]
BAD_MMS = ["MAXM", "GLED", "CFGN", "BBAR", "ALPS"]
ALL_MMS = GOOD_MMS + NEUTRAL_MMS

# Alert templates
ALERT_TEMPLATES = [
    ("VOLUME_ANOMALY", "CRITICAL", "Extreme volume spike {z:.1f}x z-score — investigate"),
    ("VOLUME_ANOMALY", "HIGH", "Volume spike {z:.1f}x z-score"),
    ("VOLUME_ANOMALY", "WARNING", "Notable volume increase RVOL {z:.1f}x"),
    ("DILUTION", "CRITICAL", "Dilution score 7 — bad MM {mm} on ask + volume divergence"),
    ("DILUTION", "HIGH_ALERT", "Dilution score 5 — prepare exit"),
    ("DILUTION", "WARNING", "Dilution score 3 — increase monitoring"),
    ("BID_COLLAPSE", "HIGH", "Bid shares dropped {pct:.0f}% in 10 minutes"),
    ("BID_COLLAPSE", "CRITICAL", "Total bid shares < 30% of entry level — exit trigger"),
    ("RATIO_CHANGE", "WARNING", "L2 imbalance dropped from {old:.1f}x to {new:.1f}x"),
    ("RATIO_CHANGE", "INFO", "L2 imbalance improved to {new:.1f}x"),
]

NOW = datetime.now(UTC)


def setup_db(conn: sqlite3.Connection):
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL UNIQUE,
            price_tier TEXT NOT NULL,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_scored TIMESTAMP,
            atm_score TEXT,
            status TEXT DEFAULT 'active',
            rejection_reason TEXT
        );
        CREATE TABLE IF NOT EXISTS l2_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            bid_levels JSON NOT NULL,
            ask_levels JSON NOT NULL,
            imbalance_ratio TEXT,
            total_bid_shares INTEGER,
            total_ask_shares INTEGER
        );
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            price TEXT NOT NULL,
            size INTEGER NOT NULL,
            side TEXT,
            mm_id TEXT
        );
        CREATE TABLE IF NOT EXISTS trade_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timestamp_entry TIMESTAMP,
            timestamp_exit TIMESTAMP,
            entry_price TEXT NOT NULL,
            exit_price TEXT,
            shares INTEGER NOT NULL,
            position_pct TEXT,
            portfolio_value_at_entry TEXT,
            l2_ratio_at_entry TEXT,
            atm_score_at_entry TEXT,
            bad_mm_present BOOLEAN DEFAULT 0,
            avg_volume_30d INTEGER,
            tracking_days INTEGER,
            exit_reason TEXT,
            pnl_usd TEXT,
            pnl_pct TEXT,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT,
            acknowledged BOOLEAN DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS daily_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            atm_score TEXT,
            stability_score TEXT,
            l2_score TEXT,
            volume_score TEXT,
            dilution_score TEXT,
            ts_score TEXT,
            ohi_score TEXT,
            UNIQUE(ticker, date)
        );
    """)


def clear_existing(conn: sqlite3.Connection):
    """Clear all data for a clean seed."""
    for table in ["candidates", "l2_snapshots", "trades", "alerts", "daily_scores"]:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()


def seed_candidates(conn: sqlite3.Connection):
    """Insert 20 candidates."""
    for ticker, tier, _price, _score, status in CANDIDATES:
        first_seen = NOW - timedelta(days=random.randint(3, 30))
        last_scored = NOW - timedelta(hours=random.randint(1, 12))
        rej = "Bad MM MAXM on ask" if status == "rejected" else None
        conn.execute(
            "INSERT OR REPLACE INTO candidates "
            "(ticker, price_tier, first_seen, last_scored, status, rejection_reason) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ticker, tier, first_seen.isoformat(), last_scored.isoformat(), status, rej),
        )
    conn.commit()
    print(f"  candidates: {len(CANDIDATES)} inserted")


def seed_daily_scores(conn: sqlite3.Connection):
    """Insert 7 days of daily scores per candidate with realistic drift."""
    rows = 0
    for ticker, _tier, _price, base_score, _status in CANDIDATES:
        for day_offset in range(7):
            date = (NOW - timedelta(days=6 - day_offset)).strftime("%Y-%m-%d")
            # Drift the score slightly each day
            drift = random.randint(-5, 5)
            atm = max(10, min(100, base_score + drift - (6 - day_offset) * 2))

            # Component scores that roughly add up to atm_score
            stability = min(15, max(0, int(atm * 0.15) + random.randint(-2, 2)))
            l2 = min(45, max(0, int(atm * 0.35) + random.randint(-5, 5)))
            volume = min(20, max(0, int(atm * 0.18) + random.randint(-3, 3)))
            dilution = min(10, max(0, int(atm * 0.12) + random.randint(-2, 2)))
            ts = min(10, max(0, int(atm * 0.10) + random.randint(-2, 2)))

            conn.execute(
                "INSERT OR REPLACE INTO daily_scores "
                "(ticker, date, atm_score, stability_score, l2_score, "
                "volume_score, dilution_score, ts_score) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (ticker, date, str(atm), str(stability), str(l2),
                 str(volume), str(dilution), str(ts)),
            )
            rows += 1
    conn.commit()
    print(f"  daily_scores: {rows} inserted (7 days x {len(CANDIDATES)} tickers)")


def seed_l2_snapshots(conn: sqlite3.Connection):
    """Insert 3 L2 snapshots per candidate with realistic bid/ask levels."""
    rows = 0
    for ticker, _tier, base_price, base_score, _status in CANDIDATES:
        price = float(base_price)
        for snap_offset in range(3):
            ts = NOW - timedelta(hours=snap_offset * 4 + random.randint(0, 3))

            # Generate 3-5 bid levels and 3-5 ask levels
            num_levels = random.randint(3, 5)

            # High-scoring stocks get better imbalance ratios
            if base_score >= 80:
                bid_multiplier = random.uniform(3.0, 8.0)
            elif base_score >= 70:
                bid_multiplier = random.uniform(1.5, 4.0)
            else:
                bid_multiplier = random.uniform(0.5, 2.0)

            bids = []
            asks = []
            total_bid = 0
            total_ask = 0

            for level in range(num_levels):
                bid_price = price - (level + 1) * price * 0.1
                ask_price = price + (level + 1) * price * 0.1
                bid_size = int(random.randint(50000, 500000) * bid_multiplier)
                ask_size = random.randint(50000, 500000)
                bid_mm = random.choice(ALL_MMS)
                # Low-score stocks sometimes have bad MMs on ask
                if base_score < 50 and random.random() < 0.4:
                    ask_mm = random.choice(BAD_MMS)
                else:
                    ask_mm = random.choice(ALL_MMS)

                bids.append({
                    "price": f"{bid_price:.4f}",
                    "size": bid_size,
                    "mm_id": bid_mm,
                })
                asks.append({
                    "price": f"{ask_price:.4f}",
                    "size": ask_size,
                    "mm_id": ask_mm,
                })
                total_bid += bid_size
                total_ask += ask_size

            ratio = total_bid / total_ask if total_ask > 0 else 0

            conn.execute(
                "INSERT INTO l2_snapshots "
                "(ticker, timestamp, bid_levels, ask_levels, "
                "imbalance_ratio, total_bid_shares, total_ask_shares) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ticker, ts.isoformat(), json.dumps(bids), json.dumps(asks),
                 f"{ratio:.2f}", total_bid, total_ask),
            )
            rows += 1
    conn.commit()
    print(f"  l2_snapshots: {rows} inserted")


def seed_trades(conn: sqlite3.Connection):
    """Insert 10-30 trades per candidate spread over recent days."""
    rows = 0
    for ticker, _tier, base_price, base_score, _status in CANDIDATES:
        price = float(base_price)
        num_trades = random.randint(10, 30)

        for _ in range(num_trades):
            ts = NOW - timedelta(
                days=random.randint(0, 6),
                hours=random.randint(0, 8),
                minutes=random.randint(0, 59),
            )
            # Slight price variation
            trade_price = price * random.uniform(0.8, 1.2)
            size = random.choice([10000, 25000, 50000, 100000, 250000, 500000, 1000000])
            # Higher score = more ask-side (bullish) trades
            if base_score >= 70:
                side = random.choices(["ask", "bid"], weights=[65, 35])[0]
            else:
                side = random.choices(["ask", "bid"], weights=[35, 65])[0]
            mm = random.choice(ALL_MMS)

            conn.execute(
                "INSERT INTO trades (ticker, timestamp, price, size, side, mm_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ticker, ts.isoformat(), f"{trade_price:.4f}", size, side, mm),
            )
            rows += 1
    conn.commit()
    print(f"  trades: {rows} inserted")


def seed_alerts(conn: sqlite3.Connection):
    """Insert realistic alerts — more for low-score and rejected stocks."""
    rows = 0
    for ticker, _tier, _price, base_score, status in CANDIDATES:
        # High-score stocks get 0-1 alerts, low-score/rejected get 2-5
        if status == "rejected":
            num_alerts = random.randint(3, 5)
        elif base_score < 50:
            num_alerts = random.randint(2, 4)
        elif base_score < 70:
            num_alerts = random.randint(1, 3)
        else:
            num_alerts = random.randint(0, 1)

        for _ in range(num_alerts):
            ts = NOW - timedelta(
                days=random.randint(0, 5),
                hours=random.randint(0, 12),
            )
            template = random.choice(ALERT_TEMPLATES)
            alert_type, severity, msg_template = template

            # Fill in template values
            msg = msg_template.format(
                z=random.uniform(2.0, 8.0),
                mm=random.choice(BAD_MMS),
                pct=random.uniform(30, 70),
                old=random.uniform(3.0, 6.0),
                new=random.uniform(1.0, 4.0),
            )

            conn.execute(
                "INSERT INTO alerts "
                "(ticker, timestamp, alert_type, severity, message, acknowledged) "
                "VALUES (?, ?, ?, ?, ?, 0)",
                (ticker, ts.isoformat(), alert_type, severity, msg),
            )
            rows += 1
    conn.commit()
    print(f"  alerts: {rows} inserted")


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))

    print(f"Seeding {DB_PATH} ...")
    setup_db(conn)
    clear_existing(conn)

    seed_candidates(conn)
    seed_daily_scores(conn)
    seed_l2_snapshots(conn)
    seed_trades(conn)
    seed_alerts(conn)

    conn.close()
    print("\nDone! Open dashboard: .venv/bin/python scripts/run_dashboard.py --port 8501")


if __name__ == "__main__":
    main()
