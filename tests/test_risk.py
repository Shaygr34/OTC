"""Tests for the risk module (Phase 6).

Covers: position sizing, OHI computation, 5 layered stop conditions.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from config.constants import PriceTier
from config.settings import RiskSettings
from src.risk.market_health import MarketHealthAnalyzer
from src.risk.position import PositionSizer
from src.risk.stops import PositionContext, StopManager, StopReason

# ── Position Sizing Tests ────────────────────────────────────────


class TestPositionSizer:
    def test_default_settings(self):
        sizer = PositionSizer()
        assert sizer.portfolio_value == Decimal("10000")

    def test_custom_settings(self):
        settings = RiskSettings(
            max_position_pct=Decimal("0.10"),
            max_loss_pct=Decimal("0.03"),
            portfolio_value=Decimal("50000"),
        )
        sizer = PositionSizer(settings)
        assert sizer.portfolio_value == Decimal("50000")

    def test_compute_basic(self):
        sizer = PositionSizer()
        result = sizer.compute(Decimal("0.0005"))
        # max_position_value = 10000 * 0.05 = 500
        assert result.max_position_value == Decimal("500")
        # max_shares = 500 / 0.0005 = 1,000,000
        assert result.max_shares == 1_000_000
        # max_loss = 10000 * 0.02 = 200
        assert result.max_loss_value == Decimal("200")
        assert result.portfolio_value == Decimal("10000")

    def test_compute_penny_price(self):
        sizer = PositionSizer()
        result = sizer.compute(Decimal("0.02"))
        assert result.max_position_value == Decimal("500")
        assert result.max_shares == 25_000

    def test_update_portfolio_value(self):
        sizer = PositionSizer()
        sizer.update_portfolio_value(Decimal("25000"))
        assert sizer.portfolio_value == Decimal("25000")
        result = sizer.compute(Decimal("0.001"))
        assert result.max_position_value == Decimal("1250")  # 25000 * 0.05

    def test_update_zero_raises(self):
        sizer = PositionSizer()
        with pytest.raises(ValueError, match="positive"):
            sizer.update_portfolio_value(Decimal("0"))

    def test_update_negative_raises(self):
        sizer = PositionSizer()
        with pytest.raises(ValueError, match="positive"):
            sizer.update_portfolio_value(Decimal("-100"))

    def test_compute_zero_price_raises(self):
        sizer = PositionSizer()
        with pytest.raises(ValueError, match="positive"):
            sizer.compute(Decimal("0"))

    def test_compute_with_ohi_full(self):
        sizer = PositionSizer()
        result = sizer.compute_with_ohi(Decimal("0.001"), Decimal("1.0"))
        base = sizer.compute(Decimal("0.001"))
        assert result.max_position_value == base.max_position_value
        assert result.max_shares == base.max_shares

    def test_compute_with_ohi_half(self):
        sizer = PositionSizer()
        result = sizer.compute_with_ohi(Decimal("0.001"), Decimal("0.5"))
        assert result.max_position_value == Decimal("250")  # 500 * 0.5
        assert result.max_shares == 250_000  # 250 / 0.001

    def test_compute_with_ohi_zero(self):
        sizer = PositionSizer()
        result = sizer.compute_with_ohi(Decimal("0.001"), Decimal("0"))
        assert result.max_position_value == Decimal("0")
        assert result.max_shares == 0


# ── OTC Health Index Tests ───────────────────────────────────────


class TestMarketHealthAnalyzer:
    @pytest.fixture
    def analyzer(self):
        return MarketHealthAnalyzer()

    def test_strong_market(self, analyzer):
        result = analyzer.compute(
            adv_decline_score=Decimal("80"),
            dollar_volume_score=Decimal("75"),
            movers_score=Decimal("60"),
            spy_score=Decimal("85"),
            sector_score=Decimal("70"),
            highs_lows_score=Decimal("65"),
        )
        assert result.regime == "STRONG"
        assert result.sizing_factor == Decimal("1")
        assert result.allow_new_entries is True
        assert result.score >= Decimal("65")

    def test_neutral_market(self, analyzer):
        result = analyzer.compute(
            adv_decline_score=Decimal("50"),
            dollar_volume_score=Decimal("50"),
            movers_score=Decimal("50"),
            spy_score=Decimal("50"),
            sector_score=Decimal("50"),
            highs_lows_score=Decimal("50"),
        )
        # score = 50 * (0.25 + 0.20 + 0.15 + 0.15 + 0.15 + 0.10) = 50
        assert result.score == Decimal("50")
        assert result.regime == "NEUTRAL"
        assert result.sizing_factor == Decimal("0.5")
        assert result.allow_new_entries is True

    def test_weak_market(self, analyzer):
        result = analyzer.compute(
            adv_decline_score=Decimal("20"),
            dollar_volume_score=Decimal("15"),
            movers_score=Decimal("30"),
            spy_score=Decimal("10"),
            sector_score=Decimal("25"),
            highs_lows_score=Decimal("20"),
        )
        assert result.regime == "WEAK"
        assert result.sizing_factor == Decimal("0")
        assert result.allow_new_entries is False

    def test_exact_strong_boundary(self, analyzer):
        # Score = 65 exactly → STRONG
        result = analyzer.compute(
            adv_decline_score=Decimal("65"),
            dollar_volume_score=Decimal("65"),
            movers_score=Decimal("65"),
            spy_score=Decimal("65"),
            sector_score=Decimal("65"),
            highs_lows_score=Decimal("65"),
        )
        assert result.score == Decimal("65")
        assert result.regime == "STRONG"

    def test_exact_neutral_boundary(self, analyzer):
        # Score = 40 exactly → NEUTRAL
        result = analyzer.compute(
            adv_decline_score=Decimal("40"),
            dollar_volume_score=Decimal("40"),
            movers_score=Decimal("40"),
            spy_score=Decimal("40"),
            sector_score=Decimal("40"),
            highs_lows_score=Decimal("40"),
        )
        assert result.score == Decimal("40")
        assert result.regime == "NEUTRAL"

    def test_below_neutral_is_weak(self, analyzer):
        result = analyzer.compute(
            adv_decline_score=Decimal("39"),
            dollar_volume_score=Decimal("39"),
            movers_score=Decimal("39"),
            spy_score=Decimal("39"),
            sector_score=Decimal("39"),
            highs_lows_score=Decimal("39"),
        )
        assert result.score < Decimal("40")
        assert result.regime == "WEAK"

    def test_clamping_over_100(self, analyzer):
        result = analyzer.compute(
            adv_decline_score=Decimal("150"),
            dollar_volume_score=Decimal("200"),
            movers_score=Decimal("100"),
            spy_score=Decimal("100"),
            sector_score=Decimal("100"),
            highs_lows_score=Decimal("100"),
        )
        assert result.score == Decimal("100")
        assert result.components["adv_decline"] == Decimal("100")
        assert result.components["dollar_volume"] == Decimal("100")

    def test_clamping_negative(self, analyzer):
        result = analyzer.compute(
            adv_decline_score=Decimal("-10"),
            dollar_volume_score=Decimal("-5"),
            movers_score=Decimal("0"),
            spy_score=Decimal("0"),
            sector_score=Decimal("0"),
            highs_lows_score=Decimal("0"),
        )
        assert result.components["adv_decline"] == Decimal("0")
        assert result.components["dollar_volume"] == Decimal("0")
        assert result.score == Decimal("0")

    def test_last_result_stored(self, analyzer):
        assert analyzer.last_result is None
        result = analyzer.compute(
            adv_decline_score=Decimal("50"),
            dollar_volume_score=Decimal("50"),
            movers_score=Decimal("50"),
            spy_score=Decimal("50"),
            sector_score=Decimal("50"),
            highs_lows_score=Decimal("50"),
        )
        assert analyzer.last_result == result

    def test_weights_sum_to_one(self):
        """Verify OHI weights sum to 1.0 (100% allocation)."""
        from config.constants import (
            OHI_WEIGHT_ADV_DECLINE,
            OHI_WEIGHT_DOLLAR_VOLUME,
            OHI_WEIGHT_HIGHS_LOWS,
            OHI_WEIGHT_MOVERS,
            OHI_WEIGHT_SECTOR,
            OHI_WEIGHT_SPY,
        )
        total = (
            OHI_WEIGHT_ADV_DECLINE + OHI_WEIGHT_DOLLAR_VOLUME
            + OHI_WEIGHT_MOVERS + OHI_WEIGHT_SPY
            + OHI_WEIGHT_SECTOR + OHI_WEIGHT_HIGHS_LOWS
        )
        assert total == Decimal("1.00")


# ── Stop Conditions Tests ────────────────────────────────────────


def _make_ctx(**overrides) -> PositionContext:
    """Create a PositionContext with sensible defaults."""
    now = datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC)
    defaults = {
        "ticker": "ABCD",
        "tier": PriceTier.TRIPS,
        "entry_price": Decimal("0.0005"),
        "current_price": Decimal("0.0005"),
        "shares": 500_000,
        "entry_time": now,
        "current_time": now + timedelta(hours=1),
        "portfolio_value": Decimal("10000"),
        "max_loss_pct": Decimal("0.02"),
        "atr": Decimal("0.0001"),
        "dilution_score": 0,
        "current_bid_shares": 1_000_000,
        "entry_bid_shares": 1_000_000,
        "is_intraday": True,
    }
    defaults.update(overrides)
    return PositionContext(**defaults)


class TestStopManager:
    @pytest.fixture
    def mgr(self):
        return StopManager()

    # ── No stops triggered ──

    def test_no_stop_when_healthy(self, mgr):
        ctx = _make_ctx()
        result = mgr.check(ctx)
        assert result.should_exit is False
        assert len(result.triggered) == 0

    # ── Hard dollar stop ──

    def test_hard_dollar_triggers(self, mgr):
        # 500k shares * (0.0005 - 0.0001) = $200 loss
        # max loss = 10000 * 0.02 = $200
        # Loss must EXCEED max, so price = 0.0000 → loss = $250
        ctx = _make_ctx(
            current_price=Decimal("0.0000"),
            entry_price=Decimal("0.0005"),
            shares=500_000,
        )
        result = mgr.check(ctx)
        assert StopReason.HARD_DOLLAR in result.triggered

    def test_hard_dollar_no_trigger_when_profitable(self, mgr):
        ctx = _make_ctx(current_price=Decimal("0.0006"))
        result = mgr.check(ctx)
        assert StopReason.HARD_DOLLAR not in result.triggered

    def test_hard_dollar_exact_boundary_no_trigger(self, mgr):
        # Loss = exactly max ($200) — should NOT trigger (must exceed)
        # 500k * (0.0005 - 0.0001) = $200 exactly
        ctx = _make_ctx(
            current_price=Decimal("0.0001"),
            entry_price=Decimal("0.0005"),
            shares=500_000,
        )
        result = mgr.check(ctx)
        assert StopReason.HARD_DOLLAR not in result.triggered

    # ── Volatility stop ──

    def test_volatility_triggers(self, mgr):
        # stop_price = 0.0005 - (0.0001 * 2) = 0.0003
        # current_price = 0.0002 < 0.0003 → triggers
        ctx = _make_ctx(
            entry_price=Decimal("0.0005"),
            current_price=Decimal("0.0002"),
            atr=Decimal("0.0001"),
        )
        result = mgr.check(ctx)
        assert StopReason.VOLATILITY in result.triggered

    def test_volatility_no_trigger_above_stop(self, mgr):
        # stop_price = 0.0003, current = 0.0004 → no trigger
        ctx = _make_ctx(
            entry_price=Decimal("0.0005"),
            current_price=Decimal("0.0004"),
            atr=Decimal("0.0001"),
        )
        result = mgr.check(ctx)
        assert StopReason.VOLATILITY not in result.triggered

    def test_volatility_zero_atr_no_trigger(self, mgr):
        ctx = _make_ctx(atr=Decimal("0"), current_price=Decimal("0.0001"))
        result = mgr.check(ctx)
        assert StopReason.VOLATILITY not in result.triggered

    # ── Time stop ──

    def test_time_stop_trips_intraday(self, mgr):
        now = datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC)
        ctx = _make_ctx(
            tier=PriceTier.TRIPS,
            entry_time=now,
            current_time=now + timedelta(hours=5),
            is_intraday=True,
        )
        result = mgr.check(ctx)
        assert StopReason.TIME in result.triggered

    def test_time_stop_trips_intraday_within_limit(self, mgr):
        now = datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC)
        ctx = _make_ctx(
            tier=PriceTier.TRIPS,
            entry_time=now,
            current_time=now + timedelta(hours=3),
            is_intraday=True,
        )
        result = mgr.check(ctx)
        assert StopReason.TIME not in result.triggered

    def test_time_stop_trips_overnight(self, mgr):
        now = datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC)
        ctx = _make_ctx(
            tier=PriceTier.TRIPS,
            entry_time=now,
            current_time=now + timedelta(days=3),
            is_intraday=False,
        )
        result = mgr.check(ctx)
        assert StopReason.TIME in result.triggered

    def test_time_stop_dubs(self, mgr):
        now = datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC)
        ctx = _make_ctx(
            tier=PriceTier.DUBS,
            entry_time=now,
            current_time=now + timedelta(days=3),
        )
        result = mgr.check(ctx)
        assert StopReason.TIME in result.triggered

    def test_time_stop_pennies(self, mgr):
        now = datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC)
        ctx = _make_ctx(
            tier=PriceTier.PENNIES,
            entry_time=now,
            current_time=now + timedelta(days=6),
        )
        result = mgr.check(ctx)
        assert StopReason.TIME in result.triggered

    def test_time_stop_pennies_within_limit(self, mgr):
        now = datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC)
        ctx = _make_ctx(
            tier=PriceTier.PENNIES,
            entry_time=now,
            current_time=now + timedelta(days=4),
        )
        result = mgr.check(ctx)
        assert StopReason.TIME not in result.triggered

    def test_time_stop_trip_zero(self, mgr):
        now = datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC)
        ctx = _make_ctx(
            tier=PriceTier.TRIP_ZERO,
            entry_time=now,
            current_time=now + timedelta(hours=5),
            is_intraday=True,
        )
        result = mgr.check(ctx)
        assert StopReason.TIME in result.triggered

    def test_time_stop_low_dubs(self, mgr):
        now = datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC)
        ctx = _make_ctx(
            tier=PriceTier.LOW_DUBS,
            entry_time=now,
            current_time=now + timedelta(days=3),
        )
        result = mgr.check(ctx)
        assert StopReason.TIME in result.triggered

    # ── Dilution stop ──

    def test_dilution_triggers(self, mgr):
        ctx = _make_ctx(dilution_score=3)
        result = mgr.check(ctx)
        assert StopReason.DILUTION in result.triggered

    def test_dilution_no_trigger_below(self, mgr):
        ctx = _make_ctx(dilution_score=2)
        result = mgr.check(ctx)
        assert StopReason.DILUTION not in result.triggered

    def test_dilution_high_score(self, mgr):
        ctx = _make_ctx(dilution_score=7)
        result = mgr.check(ctx)
        assert StopReason.DILUTION in result.triggered

    # ── L2 collapse stop ──

    def test_l2_collapse_triggers(self, mgr):
        # current = 200k, entry = 1M → 20% < 30%
        ctx = _make_ctx(
            current_bid_shares=200_000,
            entry_bid_shares=1_000_000,
        )
        result = mgr.check(ctx)
        assert StopReason.L2_COLLAPSE in result.triggered

    def test_l2_collapse_no_trigger_above_threshold(self, mgr):
        # current = 400k, entry = 1M → 40% > 30%
        ctx = _make_ctx(
            current_bid_shares=400_000,
            entry_bid_shares=1_000_000,
        )
        result = mgr.check(ctx)
        assert StopReason.L2_COLLAPSE not in result.triggered

    def test_l2_collapse_zero_entry_no_trigger(self, mgr):
        ctx = _make_ctx(
            current_bid_shares=0,
            entry_bid_shares=0,
        )
        result = mgr.check(ctx)
        assert StopReason.L2_COLLAPSE not in result.triggered

    # ── Multiple stops ──

    def test_multiple_stops_trigger(self, mgr):
        now = datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC)
        ctx = _make_ctx(
            current_price=Decimal("0.0001"),
            entry_price=Decimal("0.0005"),
            shares=1_000_000,
            dilution_score=5,
            entry_time=now,
            current_time=now + timedelta(hours=5),
            current_bid_shares=100_000,
            entry_bid_shares=1_000_000,
        )
        result = mgr.check(ctx)
        assert result.should_exit is True
        assert len(result.triggered) >= 3  # at least hard dollar + dilution + L2

    def test_details_populated(self, mgr):
        ctx = _make_ctx(dilution_score=5)
        result = mgr.check(ctx)
        assert "dilution" in result.details
        assert "score=5" in result.details["dilution"]
