"""Tests for src/scanner/ — stability metrics and screener filters.

Covers per-tier stability checks, abnormal candle detection, zero-volume
handling, screener event flow, and MockAdapter integration.
"""

from decimal import Decimal

import pytest

from config.constants import PriceTier
from src.core.event_bus import EventBus
from src.core.events import MarketDataEvent, ScannerHitEvent
from src.scanner.screener import Screener
from src.scanner.stability import (
    DailyBar,
    check_abnormal_candle,
    check_stability,
    compute_bb_width,
    compute_close_stats,
    compute_cv,
    compute_mean_volume,
    compute_natr,
    compute_price_range_ratio,
    compute_tick_range,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bar(close: str, volume: int = 100_000, spread: str = "0") -> DailyBar:
    """Create a DailyBar with sensible defaults.

    *spread* is the distance from close used for high/low/open.
    If 0, high == low == open == close (flat bar).
    """
    c = Decimal(close)
    s = Decimal(spread)
    return DailyBar(close=c, high=c + s, low=c - s, open=c, volume=volume)


def _stable_trip_bars(n: int = 20, price: str = "0.0001") -> list[DailyBar]:
    """Return *n* flat bars at a single TRIP_ZERO price level (very stable)."""
    return [_bar(price) for _ in range(n)]


def _stable_penny_bars(n: int = 20) -> list[DailyBar]:
    """Return *n* bars at $0.02 with minimal spread (stable PENNIES)."""
    return [_bar("0.02", spread="0.0001") for _ in range(n)]


def _stable_dubs_bars(n: int = 20) -> list[DailyBar]:
    """Return *n* bars at $0.005 with minimal spread (stable DUBS)."""
    return [_bar("0.005", spread="0.0001") for _ in range(n)]


def _stable_trips_bars(n: int = 20) -> list[DailyBar]:
    """Return *n* bars at $0.0007 with minimal spread (stable TRIPS)."""
    return [_bar("0.0007", spread="0.00005") for _ in range(n)]


@pytest.fixture
def bus():
    b = EventBus()
    yield b
    b.reset()


@pytest.fixture
def screener(bus):
    return Screener(bus)


def _collector(target: list):
    async def _handler(event):
        target.append(event)
    return _handler


# ===========================================================================
# Stability: individual metric tests
# ===========================================================================


class TestComputeCV:
    def test_flat_prices(self):
        closes = [Decimal("0.0001")] * 20
        assert compute_cv(closes) == Decimal("0")

    def test_varying_prices(self):
        closes = [Decimal("10"), Decimal("12"), Decimal("11"), Decimal("13")]
        cv = compute_cv(closes)
        assert cv > Decimal("0")
        assert cv < Decimal("1")

    def test_empty_returns_zero(self):
        assert compute_cv([]) == Decimal("0")

    def test_single_value_returns_zero(self):
        assert compute_cv([Decimal("5")]) == Decimal("0")


class TestComputeNATR:
    def test_flat_bars(self):
        bars = [_bar("0.0001") for _ in range(5)]
        assert compute_natr(bars) == Decimal("0")

    def test_volatile_bars(self):
        bars = [
            DailyBar(close=Decimal("10"), high=Decimal("12"), low=Decimal("8"),
                     open=Decimal("10"), volume=100),
            DailyBar(close=Decimal("11"), high=Decimal("14"), low=Decimal("9"),
                     open=Decimal("11"), volume=100),
            DailyBar(close=Decimal("10"), high=Decimal("13"), low=Decimal("7"),
                     open=Decimal("10"), volume=100),
        ]
        natr = compute_natr(bars)
        assert natr > Decimal("0")

    def test_single_bar_returns_zero(self):
        assert compute_natr([_bar("5")]) == Decimal("0")


class TestComputeBBWidth:
    def test_flat_prices(self):
        closes = [Decimal("0.0001")] * 20
        assert compute_bb_width(closes) == Decimal("0")

    def test_varying_prices(self):
        closes = [Decimal("10"), Decimal("12")] * 10
        width = compute_bb_width(closes)
        assert width > Decimal("0")

    def test_insufficient_data(self):
        assert compute_bb_width([Decimal("5")]) == Decimal("0")


class TestComputePriceRangeRatio:
    def test_flat(self):
        closes = [Decimal("0.0001")] * 10
        assert compute_price_range_ratio(closes) == Decimal("0")

    def test_range(self):
        closes = [Decimal("10"), Decimal("20")]
        ratio = compute_price_range_ratio(closes)
        # (20-10)/15 ≈ 0.667
        assert ratio > Decimal("0.6")
        assert ratio < Decimal("0.7")

    def test_empty(self):
        assert compute_price_range_ratio([]) == Decimal("0")


class TestComputeTickRange:
    def test_single_level(self):
        closes = [Decimal("0.0001")] * 20
        assert compute_tick_range(closes) == 1

    def test_multiple_levels(self):
        closes = [Decimal("0.0001"), Decimal("0.0002"), Decimal("0.0003")]
        assert compute_tick_range(closes) == 3


# ===========================================================================
# Stability: check_stability by tier
# ===========================================================================


class TestCheckStabilityTripZero:
    def test_stable_single_level(self):
        bars = _stable_trip_bars(20)
        result = check_stability(bars, PriceTier.TRIP_ZERO)
        assert result.is_stable is True
        assert result.tick_range == 1
        assert result.cv is None  # not used for TRIP_ZERO

    def test_stable_three_levels(self):
        bars = (
            [_bar("0.0001")] * 7
            + [_bar("0.0002")] * 7
            + [_bar("0.0003")] * 6
        )
        result = check_stability(bars, PriceTier.TRIP_ZERO)
        assert result.is_stable is True
        assert result.tick_range == 3

    def test_unstable_too_many_levels(self):
        bars = (
            [_bar("0.0001")] * 5
            + [_bar("0.0002")] * 5
            + [_bar("0.0003")] * 5
            + [_bar("0.0004")] * 5
        )
        result = check_stability(bars, PriceTier.TRIP_ZERO)
        assert result.is_stable is False
        assert result.tick_range == 4


class TestCheckStabilityTrips:
    def test_stable(self):
        bars = _stable_trips_bars(20)
        result = check_stability(bars, PriceTier.TRIPS)
        assert result.is_stable is True
        assert result.cv is not None
        assert result.natr is not None

    def test_unstable_high_cv(self):
        # Wildly varying prices → high CV
        bars = []
        for i in range(20):
            p = "0.0003" if i % 2 == 0 else "0.0009"
            bars.append(_bar(p, spread="0.0001"))
        result = check_stability(bars, PriceTier.TRIPS)
        assert result.is_stable is False
        assert result.cv > Decimal("0.40")


class TestCheckStabilityDubs:
    def test_stable(self):
        bars = _stable_dubs_bars(20)
        result = check_stability(bars, PriceTier.DUBS)
        assert result.is_stable is True

    def test_unstable_wide_range(self):
        bars = []
        for i in range(20):
            p = "0.001" if i % 2 == 0 else "0.009"
            bars.append(_bar(p, spread="0.001"))
        result = check_stability(bars, PriceTier.DUBS)
        assert result.is_stable is False


class TestCheckStabilityPennies:
    def test_stable(self):
        bars = _stable_penny_bars(20)
        result = check_stability(bars, PriceTier.PENNIES)
        assert result.is_stable is True

    def test_unstable_high_natr(self):
        # Large intraday swings relative to close
        bars = [
            DailyBar(
                close=Decimal("0.02"),
                high=Decimal("0.03"),
                low=Decimal("0.01"),
                open=Decimal("0.02"),
                volume=100_000,
            )
            for _ in range(20)
        ]
        result = check_stability(bars, PriceTier.PENNIES)
        assert result.is_stable is False


class TestCheckStabilityLowDubs:
    def test_uses_dubs_thresholds(self):
        """LOW_DUBS should use DUBS thresholds and pass for stable data."""
        bars = [_bar("0.002", spread="0.00005") for _ in range(20)]
        result = check_stability(bars, PriceTier.LOW_DUBS)
        assert result.is_stable is True
        assert result.tier == PriceTier.LOW_DUBS


# ===========================================================================
# Stability: active days and zero-volume handling
# ===========================================================================


class TestZeroVolumeHandling:
    def test_insufficient_active_days(self):
        bars = [_bar("0.0001", volume=100_000)] * 10
        bars += [_bar("0.0001", volume=0)] * 10
        result = check_stability(bars, PriceTier.TRIP_ZERO)
        assert result.is_stable is False
        assert result.active_days == 10

    def test_zero_volume_excluded_from_metrics(self):
        """Zero-volume days don't count toward active_days."""
        bars = [_bar("0.0001", volume=100_000)] * 18
        bars += [_bar("0.0001", volume=0)] * 2
        result = check_stability(bars, PriceTier.TRIP_ZERO)
        assert result.active_days == 18
        assert result.zero_volume_days == 2
        assert result.is_stable is True

    def test_exactly_min_active_days(self):
        bars = [_bar("0.0001", volume=100_000)] * 15
        bars += [_bar("0.0001", volume=0)] * 15
        result = check_stability(bars, PriceTier.TRIP_ZERO)
        assert result.is_stable is True
        assert result.active_days == 15

    def test_one_below_min_active_days(self):
        bars = [_bar("0.0001", volume=100_000)] * 14
        bars += [_bar("0.0001", volume=0)] * 16
        result = check_stability(bars, PriceTier.TRIP_ZERO)
        assert result.is_stable is False
        assert result.active_days == 14


class TestComputeCloseStats:
    def test_excludes_zero_volume(self):
        bars = [
            _bar("0.0001", volume=100_000),
            _bar("0.0001", volume=0),
            _bar("0.0001", volume=100_000),
        ]
        mean, std = compute_close_stats(bars)
        assert mean == Decimal("0.0001")
        assert std == Decimal("0")

    def test_empty(self):
        mean, std = compute_close_stats([])
        assert mean == Decimal("0")
        assert std == Decimal("0")


class TestComputeMeanVolume:
    def test_excludes_zero_volume(self):
        bars = [
            _bar("0.01", volume=1000),
            _bar("0.01", volume=0),
            _bar("0.01", volume=3000),
        ]
        assert compute_mean_volume(bars) == 2000

    def test_empty(self):
        assert compute_mean_volume([]) == 0


# ===========================================================================
# Abnormal candle detection
# ===========================================================================


class TestAbnormalCandleTrips:
    def test_normal_candle(self):
        bar = DailyBar(
            close=Decimal("0.0007"),
            high=Decimal("0.0008"),
            low=Decimal("0.0006"),
            open=Decimal("0.0007"),
            volume=100_000,
        )
        result = check_abnormal_candle(
            bar, PriceTier.TRIPS,
            mean_close=Decimal("0.0007"),
            std_close=Decimal("0.0001"),
            mean_volume=100_000,
        )
        assert result.is_abnormal is False

    def test_zscore_triggered(self):
        """Close far from mean → z-score exceeds 3.0."""
        bar = DailyBar(
            close=Decimal("0.0004"),
            high=Decimal("0.0008"),
            low=Decimal("0.0003"),
            open=Decimal("0.0007"),
            volume=100_000,
        )
        result = check_abnormal_candle(
            bar, PriceTier.TRIPS,
            mean_close=Decimal("0.0007"),
            std_close=Decimal("0.00005"),
            mean_volume=100_000,
        )
        assert result.is_abnormal is True
        assert result.zscore > Decimal("3.0")

    def test_abs_move_triggered(self):
        """150%+ move → absolute threshold triggered."""
        bar = DailyBar(
            close=Decimal("0.0009"),
            high=Decimal("0.0009"),
            low=Decimal("0.0003"),
            open=Decimal("0.0003"),
            volume=100_000,
        )
        result = check_abnormal_candle(
            bar, PriceTier.TRIPS,
            mean_close=Decimal("0.0004"),
            std_close=Decimal("0.0001"),
            mean_volume=100_000,
        )
        assert result.is_abnormal is True
        assert result.abs_move_pct >= Decimal("1.50")


class TestAbnormalCandleTripZero:
    def test_normal(self):
        bar = DailyBar(
            close=Decimal("0.0001"),
            high=Decimal("0.0001"),
            low=Decimal("0.0001"),
            open=Decimal("0.0001"),
            volume=100_000,
        )
        result = check_abnormal_candle(
            bar, PriceTier.TRIP_ZERO,
            mean_close=Decimal("0.0001"),
            std_close=Decimal("0"),
            mean_volume=100_000,
        )
        assert result.is_abnormal is False

    def test_tick_move_with_volume(self):
        """3+ tick move AND volume > 1.5x average → abnormal."""
        bar = DailyBar(
            close=Decimal("0.0004"),
            high=Decimal("0.0005"),
            low=Decimal("0.0001"),
            open=Decimal("0.0001"),
            volume=200_000,
        )
        result = check_abnormal_candle(
            bar, PriceTier.TRIP_ZERO,
            mean_close=Decimal("0.0001"),
            std_close=Decimal("0"),
            mean_volume=100_000,
        )
        assert result.is_abnormal is True

    def test_tick_move_without_volume_not_abnormal(self):
        """3 tick move but volume below 1.5x → not abnormal."""
        bar = DailyBar(
            close=Decimal("0.0004"),
            high=Decimal("0.0005"),
            low=Decimal("0.0001"),
            open=Decimal("0.0001"),
            volume=100_000,
        )
        result = check_abnormal_candle(
            bar, PriceTier.TRIP_ZERO,
            mean_close=Decimal("0.0001"),
            std_close=Decimal("0"),
            mean_volume=100_000,
        )
        assert result.is_abnormal is False


class TestAbnormalCandlePennies:
    def test_normal(self):
        bar = _bar("0.02", spread="0.001")
        result = check_abnormal_candle(
            bar, PriceTier.PENNIES,
            mean_close=Decimal("0.02"),
            std_close=Decimal("0.001"),
            mean_volume=100_000,
        )
        assert result.is_abnormal is False

    def test_large_move(self):
        """30%+ move → triggered for PENNIES."""
        bar = DailyBar(
            close=Decimal("0.026"),
            high=Decimal("0.027"),
            low=Decimal("0.019"),
            open=Decimal("0.019"),
            volume=100_000,
        )
        result = check_abnormal_candle(
            bar, PriceTier.PENNIES,
            mean_close=Decimal("0.02"),
            std_close=Decimal("0.001"),
            mean_volume=100_000,
        )
        assert result.is_abnormal is True


class TestBodyRangeRatio:
    def test_directional_candle(self):
        """Body > 60% of range → directional."""
        bar = DailyBar(
            close=Decimal("0.0009"),
            high=Decimal("0.0009"),
            low=Decimal("0.0003"),
            open=Decimal("0.0003"),
            volume=100_000,
        )
        result = check_abnormal_candle(
            bar, PriceTier.TRIPS,
            mean_close=Decimal("0.0006"),
            std_close=Decimal("0.0001"),
            mean_volume=100_000,
        )
        assert result.directional is True
        assert result.body_range_ratio == Decimal("1")

    def test_doji_not_directional(self):
        """Open == close → body is zero → not directional."""
        bar = DailyBar(
            close=Decimal("0.0005"),
            high=Decimal("0.0007"),
            low=Decimal("0.0003"),
            open=Decimal("0.0005"),
            volume=100_000,
        )
        result = check_abnormal_candle(
            bar, PriceTier.TRIPS,
            mean_close=Decimal("0.0005"),
            std_close=Decimal("0.0001"),
            mean_volume=100_000,
        )
        assert result.directional is False
        assert result.body_range_ratio == Decimal("0")


# ===========================================================================
# Screener: integration tests
# ===========================================================================


class TestScreenerEvaluation:
    async def test_pass_publishes_scanner_hit(self, screener, bus):
        hits = []
        bus.subscribe(ScannerHitEvent, _collector(hits))

        for b in _stable_trip_bars(20):
            screener.add_daily_bar("ABCD", b)

        passed = await screener.evaluate("ABCD", Decimal("0.0001"), 100_000)
        assert passed is True
        assert len(hits) == 1
        assert hits[0].ticker == "ABCD"
        assert hits[0].price_tier == "TRIP_ZERO"

    async def test_no_tier_returns_false(self, screener):
        # $1.00 is outside all OTC tiers
        passed = await screener.evaluate("ABCD", Decimal("1.00"), 100_000)
        assert passed is False

    async def test_no_bars_returns_false(self, screener):
        passed = await screener.evaluate("ABCD", Decimal("0.0001"), 100_000)
        assert passed is False

    async def test_unstable_returns_false(self, screener, bus):
        hits = []
        bus.subscribe(ScannerHitEvent, _collector(hits))

        # 4 distinct levels → unstable for TRIP_ZERO
        bars = (
            [_bar("0.0001")] * 5
            + [_bar("0.0002")] * 5
            + [_bar("0.0003")] * 5
            + [_bar("0.0004")] * 5
        )
        for b in bars:
            screener.add_daily_bar("ABCD", b)

        passed = await screener.evaluate("ABCD", Decimal("0.0001"), 100_000)
        assert passed is False
        assert len(hits) == 0

    async def test_abnormal_candle_returns_false(self, screener, bus):
        hits = []
        bus.subscribe(ScannerHitEvent, _collector(hits))

        # 19 stable bars + 1 abnormal spike
        bars = _stable_trips_bars(19)
        bars.append(DailyBar(
            close=Decimal("0.0009"),
            high=Decimal("0.0009"),
            low=Decimal("0.0003"),
            open=Decimal("0.0003"),
            volume=500_000,
        ))
        for b in bars:
            screener.add_daily_bar("EFGH", b)

        passed = await screener.evaluate("EFGH", Decimal("0.0007"), 100_000)
        assert passed is False
        assert len(hits) == 0

    async def test_rejected_symbol_skipped(self, screener, bus):
        hits = []
        bus.subscribe(ScannerHitEvent, _collector(hits))

        for b in _stable_trip_bars(20):
            screener.add_daily_bar("ABCD", b)

        screener.reject("ABCD", "manual rejection")
        passed = await screener.evaluate("ABCD", Decimal("0.0001"), 100_000)
        assert passed is False
        assert len(hits) == 0

    async def test_unreject_allows_evaluation(self, screener, bus):
        hits = []
        bus.subscribe(ScannerHitEvent, _collector(hits))

        for b in _stable_trip_bars(20):
            screener.add_daily_bar("ABCD", b)

        screener.reject("ABCD", "test")
        screener.unreject("ABCD")
        passed = await screener.evaluate("ABCD", Decimal("0.0001"), 100_000)
        assert passed is True


class TestScreenerLastResult:
    async def test_stores_last_result(self, screener):
        for b in _stable_trip_bars(20):
            screener.add_daily_bar("ABCD", b)
        await screener.evaluate("ABCD", Decimal("0.0001"), 100_000)
        result = screener.get_last_result("ABCD")
        assert result is not None
        assert result.is_stable is True

    async def test_no_result_before_eval(self, screener):
        assert screener.get_last_result("ABCD") is None


class TestScreenerBarManagement:
    def test_rolling_window_trims(self, screener):
        for _ in range(40):
            screener.add_daily_bar("ABCD", _bar("0.0001"))
        assert len(screener.get_bars("ABCD")) == 30

    def test_empty_bars(self, screener):
        assert screener.get_bars("ABCD") == []


class TestScreenerEventBusIntegration:
    async def test_market_data_triggers_evaluation(self, screener, bus):
        """When subscribed, MarketDataEvent triggers the screener."""
        hits = []
        bus.subscribe(ScannerHitEvent, _collector(hits))
        screener.start()

        for b in _stable_trip_bars(20):
            screener.add_daily_bar("ABCD", b)

        # Simulate a MarketDataEvent being published
        event = MarketDataEvent(
            ticker="ABCD",
            price=Decimal("0.0001"),
            bid=Decimal("0.0001"),
            ask=Decimal("0.0002"),
            volume=100_000,
        )
        await bus.publish(event)

        assert len(hits) == 1
        assert hits[0].ticker == "ABCD"


class TestScreenerMultipleTiers:
    async def test_pennies_pass(self, screener, bus):
        hits = []
        bus.subscribe(ScannerHitEvent, _collector(hits))

        for b in _stable_penny_bars(20):
            screener.add_daily_bar("PENY", b)

        passed = await screener.evaluate("PENY", Decimal("0.02"), 100_000)
        assert passed is True
        assert hits[0].price_tier == "PENNIES"

    async def test_dubs_pass(self, screener, bus):
        hits = []
        bus.subscribe(ScannerHitEvent, _collector(hits))

        for b in _stable_dubs_bars(20):
            screener.add_daily_bar("DUBS", b)

        passed = await screener.evaluate("DUBS", Decimal("0.005"), 100_000)
        assert passed is True
        assert hits[0].price_tier == "DUBS"

    async def test_trips_pass(self, screener, bus):
        hits = []
        bus.subscribe(ScannerHitEvent, _collector(hits))

        for b in _stable_trips_bars(20):
            screener.add_daily_bar("TRIP", b)

        passed = await screener.evaluate("TRIP", Decimal("0.0007"), 100_000)
        assert passed is True
        assert hits[0].price_tier == "TRIPS"
