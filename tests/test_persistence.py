"""Tests for PersistenceSubscriber — event → DB write contract."""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.event_bus import EventBus
from src.core.events import (
    AlertEvent,
    AnalysisCompleteEvent,
    DilutionAlertEvent,
    L2UpdateEvent,
    ScannerHitEvent,
    TradeEvent,
)
from src.database.persistence import PersistenceSubscriber
from src.database.repository import Repository
from src.database.schema import (
    Alert,
    Base,
    Candidate,
    DailyScore,
    L2SnapshotRow,
    TradeRow,
)


@pytest.fixture
async def db_setup():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    yield engine, sf
    await engine.dispose()


@pytest.fixture
def bus():
    b = EventBus()
    yield b
    b.reset()


@pytest.fixture
async def persistence(db_setup, bus):
    _, sf = db_setup
    repo = Repository(sf)
    sub = PersistenceSubscriber(repo, bus)
    sub.start()
    return sub


# ── L2UpdateEvent ──


async def test_l2_update_persists(db_setup, bus, persistence):
    _engine, sf = db_setup
    event = L2UpdateEvent(
        ticker="ABCD",
        bid_levels=((Decimal("0.0003"), 100000, "ETRF"),),
        ask_levels=((Decimal("0.0004"), 50000, "MAXM"),),
    )
    await bus.publish(event)

    async with sf() as session:
        rows = (await session.execute(select(L2SnapshotRow))).scalars().all()
        assert len(rows) == 1
        assert rows[0].ticker == "ABCD"
        assert rows[0].total_bid_shares == 100000
        assert rows[0].total_ask_shares == 50000
        assert rows[0].bid_levels[0]["mm_id"] == "ETRF"


# ── TradeEvent ──


async def test_trade_persists(db_setup, bus, persistence):
    _engine, sf = db_setup
    event = TradeEvent(
        ticker="EFGH",
        price=Decimal("0.0005"),
        size=50000,
        side="ask",
        mm_id="NITE",
    )
    await bus.publish(event)

    async with sf() as session:
        rows = (await session.execute(select(TradeRow))).scalars().all()
        assert len(rows) == 1
        assert rows[0].ticker == "EFGH"
        assert rows[0].price == "0.0005"
        assert rows[0].side == "ask"
        assert rows[0].mm_id == "NITE"


# ── AlertEvent ──


async def test_alert_persists(db_setup, bus, persistence):
    _engine, sf = db_setup
    event = AlertEvent(
        ticker="IJKL",
        alert_type="VOLUME_ANOMALY",
        severity="HIGH",
        message="Volume spike 5x average",
    )
    await bus.publish(event)

    async with sf() as session:
        rows = (await session.execute(select(Alert))).scalars().all()
        assert len(rows) == 1
        assert rows[0].alert_type == "VOLUME_ANOMALY"
        assert rows[0].severity == "HIGH"


# ── DilutionAlertEvent ──


async def test_dilution_alert_persists(db_setup, bus, persistence):
    _engine, sf = db_setup
    event = DilutionAlertEvent(
        ticker="MNOP",
        dilution_score=5,
        severity="HIGH_ALERT",
        signals=("bad_mm_on_ask", "volume_spike"),
        message="Dilution score 5 — prepare exit",
    )
    await bus.publish(event)

    async with sf() as session:
        rows = (await session.execute(select(Alert))).scalars().all()
        assert len(rows) == 1
        assert rows[0].alert_type == "DILUTION"
        assert rows[0].severity == "HIGH_ALERT"


# ── AnalysisCompleteEvent ──


async def test_analysis_complete_persists(db_setup, bus, persistence):
    _engine, sf = db_setup
    event = AnalysisCompleteEvent(
        ticker="QRST",
        atm_score=Decimal("85"),
        stability_score=Decimal("15"),
        l2_score=Decimal("20"),
        volume_score=Decimal("10"),
        dilution_score=Decimal("10"),
        ts_score=Decimal("10"),
    )
    await bus.publish(event)

    async with sf() as session:
        rows = (await session.execute(select(DailyScore))).scalars().all()
        assert len(rows) == 1
        assert rows[0].ticker == "QRST"
        assert rows[0].atm_score == "85"


async def test_daily_score_upsert_overwrites(db_setup, bus, persistence):
    _engine, sf = db_setup
    event1 = AnalysisCompleteEvent(
        ticker="UVWX",
        atm_score=Decimal("70"),
        stability_score=Decimal("10"),
        l2_score=Decimal("15"),
        volume_score=Decimal("8"),
        dilution_score=Decimal("7"),
        ts_score=Decimal("5"),
    )
    event2 = AnalysisCompleteEvent(
        ticker="UVWX",
        atm_score=Decimal("85"),
        stability_score=Decimal("15"),
        l2_score=Decimal("20"),
        volume_score=Decimal("10"),
        dilution_score=Decimal("10"),
        ts_score=Decimal("10"),
    )
    await bus.publish(event1)
    await bus.publish(event2)

    async with sf() as session:
        rows = (await session.execute(select(DailyScore))).scalars().all()
        assert len(rows) == 1  # upsert, not duplicate
        assert rows[0].atm_score == "85"  # second value wins


# ── ScannerHitEvent ──


async def test_scanner_hit_persists_candidate(db_setup, bus, persistence):
    _engine, sf = db_setup
    event = ScannerHitEvent(
        ticker="AAAA",
        price_tier="TRIPS",
        price=Decimal("0.0003"),
        volume=100000,
    )
    await bus.publish(event)

    async with sf() as session:
        rows = (await session.execute(select(Candidate))).scalars().all()
        assert len(rows) == 1
        assert rows[0].ticker == "AAAA"
        assert rows[0].price_tier == "TRIPS"


async def test_scanner_hit_deduplicates(db_setup, bus, persistence):
    _engine, sf = db_setup
    event = ScannerHitEvent(
        ticker="BBBB",
        price_tier="DUBS",
        price=Decimal("0.005"),
        volume=200000,
    )
    # Publish same ticker twice
    await bus.publish(event)
    await bus.publish(event)

    async with sf() as session:
        rows = (await session.execute(select(Candidate))).scalars().all()
        assert len(rows) == 1  # seen set prevents duplicate insert
