"""Seed the SQLite database with realistic demo data for dashboard testing."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from src.database.repository import Repository, get_engine, get_session_factory
from src.database.schema import create_all_tables

# Demo tickers with varied profiles
CANDIDATES = [
    ("ABCD", "TRIPS", Decimal("92"), "active"),
    ("EFGH", "TRIPS", Decimal("85"), "active"),
    ("IJKL", "DUBS", Decimal("78"), "watching"),
    ("MNOP", "PENNIES", Decimal("73"), "watching"),
    ("QRST", "TRIP_ZERO", Decimal("68"), "active"),
    ("UVWX", "TRIPS", Decimal("45"), "rejected"),
    ("YZAB", "LOW_DUBS", Decimal("81"), "active"),
    ("CDEF", "DUBS", Decimal("55"), "rejected"),
    ("GHIJ", "PENNIES", Decimal("88"), "trading"),
    ("KLMN", "TRIPS", Decimal("76"), "watching"),
]

ALERT_TYPES = [
    ("ABCD", "VOLUME_ANOMALY", "WARNING", "Volume spike: z=3.2, RVOL=4.1, vol=890,000"),
    ("ABCD", "VOLUME_ANOMALY", "HIGH", "Extreme volume: z=5.8, RVOL=8.3, vol=2,100,000"),
    ("EFGH", "BID_COLLAPSE", "CRITICAL", "Bid collapsed: 1.2M → 180K shares (-85%)"),
    ("EFGH", "VOLUME_ANOMALY", "WARNING", "Volume spike: z=2.9, RVOL=3.5, vol=450,000"),
    ("IJKL", "RATIO_CHANGE", "INFO", "Buy/sell ratio shifted: 2.8 → 1.4"),
    ("GHIJ", "VOLUME_ANOMALY", "WARNING", "Volume spike: z=3.1, RVOL=2.8, vol=320,000"),
    ("MNOP", "VOLUME_ANOMALY", "INFO", "Notable volume: z=2.2, RVOL=1.9, vol=95,000"),
    ("UVWX", "BID_COLLAPSE", "CRITICAL", "Bid collapsed: 800K → 90K shares (-89%)"),
    ("UVWX", "VOLUME_ANOMALY", "HIGH", "Extreme volume: z=6.1, RVOL=9.2, vol=3,500,000"),
    ("YZAB", "RATIO_CHANGE", "WARNING", "Buy/sell ratio dropped: 3.1 → 1.2"),
    ("QRST", "VOLUME_ANOMALY", "INFO", "Notable volume: z=2.1, RVOL=1.8, vol=120,000"),
    ("KLMN", "VOLUME_ANOMALY", "WARNING", "Volume spike: z=2.8, RVOL=2.5, vol=280,000"),
    ("CDEF", "BID_COLLAPSE", "HIGH", "Bid weakening: 500K → 200K shares (-60%)"),
    ("ABCD", "RATIO_CHANGE", "INFO", "Buy/sell ratio improved: 1.8 → 3.2"),
    ("GHIJ", "VOLUME_ANOMALY", "HIGH", "Extreme volume: z=4.9, RVOL=6.1, vol=1,800,000"),
]


async def seed():
    engine = get_engine("sqlite+aiosqlite:///data/atm.db")
    await create_all_tables(engine)
    repo = Repository(get_session_factory(engine))

    now = datetime.now(UTC)

    # Candidates
    for ticker, tier, score, status in CANDIDATES:
        await repo.add_candidate(ticker, tier, score, status)
    print(f"Seeded {len(CANDIDATES)} candidates")

    # Alerts (spread over last 7 days)
    for i, (ticker, atype, severity, msg) in enumerate(ALERT_TYPES):
        # Hack: save_alert uses current timestamp, so we insert directly
        from src.database.schema import Alert
        from sqlalchemy.ext.asyncio import async_sessionmaker
        sf = get_session_factory(engine)
        async with sf() as session:
            row = Alert(
                ticker=ticker,
                alert_type=atype,
                severity=severity,
                message=msg,
                timestamp=now - timedelta(hours=i * 6),
            )
            session.add(row)
            await session.commit()
    print(f"Seeded {len(ALERT_TYPES)} alerts")

    # Daily scores for each candidate (last 14 days)
    import random
    random.seed(42)
    for ticker, tier, base_score, _ in CANDIDATES:
        base = float(base_score)
        for day_offset in range(14):
            date = (now - timedelta(days=13 - day_offset)).strftime("%Y-%m-%d")
            noise = random.uniform(-8, 8)
            atm = max(0, min(100, base + noise))
            stability = random.uniform(8, 15)
            l2 = random.uniform(10, 45)
            volume = random.uniform(5, 20)
            dilution = random.uniform(0, 10)
            ts = random.uniform(3, 10)
            ohi = random.uniform(40, 85)
            await repo.save_daily_score(
                ticker=ticker,
                date=date,
                atm_score=Decimal(str(round(atm, 1))),
                stability_score=Decimal(str(round(stability, 1))),
                l2_score=Decimal(str(round(l2, 1))),
                volume_score=Decimal(str(round(volume, 1))),
                dilution_score=Decimal(str(round(dilution, 1))),
                ts_score=Decimal(str(round(ts, 1))),
                ohi_score=Decimal(str(round(ohi, 1))),
            )
    print(f"Seeded {len(CANDIDATES) * 14} daily scores")

    # L2 snapshots for top candidates (last 3 days, multiple per day)
    top_tickers = ["ABCD", "EFGH", "GHIJ", "YZAB"]
    l2_count = 0
    for ticker in top_tickers:
        for hour_offset in range(0, 72, 4):  # every 4 hours for 3 days
            ts = now - timedelta(hours=72 - hour_offset)
            bid_total = random.randint(200_000, 2_000_000)
            ask_total = random.randint(50_000, 800_000)
            ratio = Decimal(str(round(bid_total / ask_total, 2)))
            bid_levels = [
                {"price": "0.0003", "size": bid_total // 3, "mm_id": "ETRF"},
                {"price": "0.0002", "size": bid_total // 3, "mm_id": "NITE"},
                {"price": "0.0001", "size": bid_total // 3, "mm_id": "VIRT"},
            ]
            ask_levels = [
                {"price": "0.0004", "size": ask_total // 2, "mm_id": "OTCN"},
                {"price": "0.0005", "size": ask_total // 2, "mm_id": "CDEL"},
            ]
            await repo.save_l2_snapshot(
                ticker=ticker,
                timestamp=ts,
                bid_levels=bid_levels,
                ask_levels=ask_levels,
                imbalance_ratio=ratio,
                total_bid_shares=bid_total,
                total_ask_shares=ask_total,
            )
            l2_count += 1
    print(f"Seeded {l2_count} L2 snapshots")

    # Trades for top candidates
    trade_count = 0
    for ticker in top_tickers:
        for day_offset in range(7):
            day_ts = now - timedelta(days=6 - day_offset)
            num_trades = random.randint(15, 60)
            for _ in range(num_trades):
                side = random.choice(["ask", "ask", "ask", "bid", "bid", "unknown"])
                price = Decimal(str(random.choice(
                    ["0.0003", "0.0003", "0.0004", "0.0002", "0.0003"]
                )))
                size = random.randint(10_000, 500_000)
                trade_ts = day_ts + timedelta(
                    hours=random.randint(9, 15),
                    minutes=random.randint(0, 59),
                )
                await repo.save_trade(
                    ticker=ticker,
                    timestamp=trade_ts,
                    price=price,
                    size=size,
                    side=side,
                    mm_id=random.choice(["ETRF", "NITE", "VIRT", "OTCN", ""]),
                )
                trade_count += 1
    print(f"Seeded {trade_count} trades")

    await engine.dispose()
    print("\nDone! Refresh the dashboard.")


if __name__ == "__main__":
    asyncio.run(seed())
