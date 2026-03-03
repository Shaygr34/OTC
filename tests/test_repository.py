"""Tests for src/database/repository.py — CRUD round-trips on in-memory SQLite."""

from datetime import UTC, datetime
from decimal import Decimal

from src.database.repository import Repository


async def test_add_and_get_candidate(session_factory):
    repo = Repository(session_factory)

    candidate = await repo.add_candidate(
        ticker="ABCD", price_tier="TRIPS", atm_score=Decimal("85"), status="active"
    )
    assert candidate.id is not None
    assert candidate.ticker == "ABCD"
    assert candidate.atm_score == "85"

    results = await repo.get_candidates_by_status("active")
    assert len(results) == 1
    assert results[0].ticker == "ABCD"


async def test_get_candidates_empty(session_factory):
    repo = Repository(session_factory)
    results = await repo.get_candidates_by_status("active")
    assert results == []


async def test_save_l2_snapshot(session_factory):
    repo = Repository(session_factory)
    now = datetime.now(UTC)

    snap = await repo.save_l2_snapshot(
        ticker="ABCD",
        timestamp=now,
        bid_levels=[{"price": "0.0003", "size": 1_000_000, "mm_id": "NITE"}],
        ask_levels=[{"price": "0.0004", "size": 200_000, "mm_id": "MAXM"}],
        imbalance_ratio=Decimal("5.0"),
        total_bid_shares=1_000_000,
        total_ask_shares=200_000,
    )
    assert snap.id is not None
    assert snap.ticker == "ABCD"
    assert snap.imbalance_ratio == "5.0"


async def test_save_trade(session_factory):
    repo = Repository(session_factory)
    now = datetime.now(UTC)

    trade = await repo.save_trade(
        ticker="ABCD",
        timestamp=now,
        price=Decimal("0.0003"),
        size=500_000,
        side="bid",
        mm_id="NITE",
    )
    assert trade.id is not None
    assert trade.price == "0.0003"
    assert trade.size == 500_000


async def test_log_trade(session_factory):
    repo = Repository(session_factory)

    log = await repo.log_trade(
        ticker="ABCD",
        entry_price=Decimal("0.0003"),
        shares=1_000_000,
        exit_price=Decimal("0.0004"),
        pnl_usd=Decimal("100.00"),
        exit_reason="TARGET",
    )
    assert log.id is not None
    assert log.entry_price == "0.0003"
    assert log.exit_price == "0.0004"
    assert log.exit_reason == "TARGET"


async def test_save_alert(session_factory):
    repo = Repository(session_factory)

    alert = await repo.save_alert(
        ticker="ABCD",
        alert_type="VOLUME_ANOMALY",
        severity="HIGH",
        message="Volume spike 5x average",
    )
    assert alert.id is not None
    assert alert.alert_type == "VOLUME_ANOMALY"
    assert alert.severity == "HIGH"


async def test_save_daily_score(session_factory):
    repo = Repository(session_factory)

    score = await repo.save_daily_score(
        ticker="ABCD",
        date="2024-01-15",
        atm_score=Decimal("82"),
        stability_score=Decimal("14"),
        l2_score=Decimal("18"),
        volume_score=Decimal("9"),
        dilution_score=Decimal("10"),
        ts_score=Decimal("8"),
        ohi_score=Decimal("72"),
    )
    assert score.id is not None
    assert score.atm_score == "82"
    assert score.date == "2024-01-15"


async def test_schema_creates_without_errors(engine):
    """Schema should already be created by the conftest fixture — just verify."""
    from src.database.schema import create_all_tables

    # Running create_all_tables again should be idempotent
    await create_all_tables(engine)
