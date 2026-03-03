"""Tests for src/core/models.py — validation, Decimal, immutability."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.core.models import CandidateScore, L2Level, L2Snapshot, OHIScore, Trade


class TestL2Level:
    def test_create(self):
        level = L2Level(price=Decimal("0.0003"), size=500_000, mm_id="MAXM")
        assert level.price == Decimal("0.0003")
        assert level.size == 500_000
        assert level.mm_id == "MAXM"

    def test_frozen(self):
        level = L2Level(price=Decimal("0.0003"), size=500_000, mm_id="MAXM")
        with pytest.raises(ValidationError):
            level.price = Decimal("0.0004")


class TestL2Snapshot:
    def test_create(self):
        now = datetime.now(UTC)
        snap = L2Snapshot(
            ticker="ABCD",
            timestamp=now,
            bid_levels=(L2Level(price=Decimal("0.0003"), size=1_000_000, mm_id="NITE"),),
            ask_levels=(L2Level(price=Decimal("0.0004"), size=200_000, mm_id="MAXM"),),
            imbalance_ratio=Decimal("5.0"),
            total_bid_shares=1_000_000,
            total_ask_shares=200_000,
        )
        assert snap.imbalance_ratio == Decimal("5.0")

    def test_frozen(self):
        now = datetime.now(UTC)
        snap = L2Snapshot(
            ticker="ABCD",
            timestamp=now,
            bid_levels=(),
            ask_levels=(),
            imbalance_ratio=Decimal("1.0"),
            total_bid_shares=0,
            total_ask_shares=0,
        )
        with pytest.raises(ValidationError):
            snap.ticker = "XXXX"


class TestTrade:
    def test_create(self):
        trade = Trade(
            ticker="ABCD",
            timestamp=datetime.now(UTC),
            price=Decimal("0.0003"),
            size=100_000,
            side="bid",
            mm_id="NITE",
        )
        assert trade.price == Decimal("0.0003")
        assert trade.side == "bid"

    def test_decimal_from_string(self):
        """Pydantic should coerce string to Decimal."""
        trade = Trade(
            ticker="ABCD",
            timestamp=datetime.now(UTC),
            price="0.0003",
            size=100_000,
            side="ask",
        )
        assert isinstance(trade.price, Decimal)


class TestCandidateScore:
    def test_create(self):
        score = CandidateScore(
            ticker="ABCD",
            atm_score=Decimal("82"),
            stability_score=Decimal("14"),
            l2_score=Decimal("18"),
            volume_score=Decimal("9"),
            dilution_score=Decimal("10"),
            ts_score=Decimal("8"),
        )
        assert score.atm_score == Decimal("82")

    def test_frozen(self):
        score = CandidateScore(
            ticker="ABCD",
            atm_score=Decimal("82"),
            stability_score=Decimal("14"),
            l2_score=Decimal("18"),
            volume_score=Decimal("9"),
            dilution_score=Decimal("10"),
            ts_score=Decimal("8"),
        )
        with pytest.raises(ValidationError):
            score.atm_score = Decimal("50")


class TestOHIScore:
    def test_create(self):
        ohi = OHIScore(
            value=Decimal("72"),
            components={
                "adv_decline": Decimal("20"),
                "dollar_volume": Decimal("15"),
                "movers": Decimal("12"),
                "spy": Decimal("10"),
                "sector": Decimal("10"),
                "highs_lows": Decimal("5"),
            },
        )
        assert ohi.value == Decimal("72")
        assert len(ohi.components) == 6
