"""Stability metrics for OTC candidate screening.

Pure-computation module — takes daily price/volume records, returns metrics.
All arithmetic uses Decimal. Never float.

Metrics by tier:
  TRIP_ZERO: Tick Range Ratio (TRR) — count of distinct price levels.
  TRIPS/DUBS/PENNIES: CV, NATR, Bollinger Band Width, Price Range Ratio.
  LOW_DUBS: Uses DUBS thresholds (closest match).
"""

from dataclasses import dataclass
from decimal import Decimal

from config.constants import (
    ABNORMAL_CANDLE_THRESHOLDS,
    CANDLE_BODY_RANGE_RATIO_MIN,
    MIN_ACTIVE_TRADING_DAYS,
    STABILITY_THRESHOLDS,
    TRIP_ZERO_MAX_TICK_LEVELS,
    TRIP_ZERO_VOLUME_MULTIPLIER,
    AbnormalCandleThresholds,
    PriceTier,
    StabilityThresholds,
)

# Decimal constants used in calculations
_ZERO = Decimal("0")
_ONE = Decimal("1")
_TWO = Decimal("2")


@dataclass(frozen=True)
class DailyBar:
    """Single day's OHLCV data for a symbol."""

    close: Decimal
    high: Decimal
    low: Decimal
    open: Decimal
    volume: int


@dataclass(frozen=True)
class StabilityResult:
    """Output of stability analysis for a single symbol."""

    is_stable: bool
    tier: PriceTier
    active_days: int
    zero_volume_days: int
    # Metric values (set to None when not applicable for the tier)
    cv: Decimal | None = None
    natr: Decimal | None = None
    bb_width: Decimal | None = None
    price_range_ratio: Decimal | None = None
    tick_range: int | None = None  # TRIP_ZERO only


@dataclass(frozen=True)
class AbnormalCandleResult:
    """Output of abnormal candle detection for a single bar."""

    is_abnormal: bool
    abs_move_pct: Decimal
    zscore: Decimal
    body_range_ratio: Decimal
    directional: bool  # True if body/range ratio exceeds threshold


# ---------------------------------------------------------------------------
# Helper: filter active (non-zero volume) days
# ---------------------------------------------------------------------------

def _active_bars(bars: list[DailyBar]) -> list[DailyBar]:
    return [b for b in bars if b.volume > 0]


# ---------------------------------------------------------------------------
# Metric: Coefficient of Variation (std / mean) on closing prices
# ---------------------------------------------------------------------------

def compute_cv(closes: list[Decimal]) -> Decimal:
    """Coefficient of Variation of closing prices.

    Returns 0 if fewer than 2 data points or mean is zero.
    """
    n = len(closes)
    if n < 2:
        return _ZERO
    mean = sum(closes) / n
    if mean == _ZERO:
        return _ZERO
    variance = sum((c - mean) ** 2 for c in closes) / (n - _ONE)
    std = variance.sqrt()
    return std / mean


# ---------------------------------------------------------------------------
# Metric: Normalized ATR (ATR / close)
# ---------------------------------------------------------------------------

def compute_natr(bars: list[DailyBar]) -> Decimal:
    """Normalized Average True Range over the given bars.

    True Range = max(high-low, |high-prev_close|, |low-prev_close|).
    NATR = ATR / last_close.
    Returns 0 if fewer than 2 bars or last close is zero.
    """
    if len(bars) < 2:
        return _ZERO
    true_ranges: list[Decimal] = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        h_l = bars[i].high - bars[i].low
        h_pc = abs(bars[i].high - prev_close)
        l_pc = abs(bars[i].low - prev_close)
        true_ranges.append(max(h_l, h_pc, l_pc))

    if not true_ranges:
        return _ZERO
    atr = sum(true_ranges) / len(true_ranges)
    last_close = bars[-1].close
    if last_close == _ZERO:
        return _ZERO
    return atr / last_close


# ---------------------------------------------------------------------------
# Metric: Bollinger Band Width = (upper - lower) / middle
# ---------------------------------------------------------------------------

def compute_bb_width(closes: list[Decimal], period: int = 20) -> Decimal:
    """Bollinger Band Width using 2-standard-deviation bands.

    Uses last *period* closes (or all if fewer). Returns 0 if
    insufficient data or middle band is zero.
    """
    window = closes[-period:] if len(closes) >= period else closes
    n = len(window)
    if n < 2:
        return _ZERO
    mean = sum(window) / n
    if mean == _ZERO:
        return _ZERO
    variance = sum((c - mean) ** 2 for c in window) / (n - _ONE)
    std = variance.sqrt()
    upper = mean + _TWO * std
    lower = mean - _TWO * std
    return (upper - lower) / mean


# ---------------------------------------------------------------------------
# Metric: 30-day Price Range Ratio = (max - min) / mean
# ---------------------------------------------------------------------------

def compute_price_range_ratio(closes: list[Decimal]) -> Decimal:
    """Price Range Ratio = (max_close - min_close) / mean_close."""
    if not closes:
        return _ZERO
    mean = sum(closes) / len(closes)
    if mean == _ZERO:
        return _ZERO
    return (max(closes) - min(closes)) / mean


# ---------------------------------------------------------------------------
# Metric: Tick Range Ratio (TRIP_ZERO only)
# ---------------------------------------------------------------------------

def compute_tick_range(closes: list[Decimal]) -> int:
    """Count distinct price levels in the close series."""
    return len(set(closes))


# ---------------------------------------------------------------------------
# Stability check: main entry point
# ---------------------------------------------------------------------------

def check_stability(bars: list[DailyBar], tier: PriceTier) -> StabilityResult:
    """Run the appropriate stability check for the given price tier.

    Args:
        bars: 30 days of OHLCV data (may contain zero-volume days).
        tier: The price tier from ``get_tier()``.

    Returns:
        StabilityResult with ``is_stable`` flag and all computed metrics.
    """
    active = _active_bars(bars)
    active_days = len(active)
    zero_volume_days = len(bars) - active_days

    # Insufficient trading activity → not stable
    if active_days < MIN_ACTIVE_TRADING_DAYS:
        return StabilityResult(
            is_stable=False,
            tier=tier,
            active_days=active_days,
            zero_volume_days=zero_volume_days,
        )

    if tier == PriceTier.TRIP_ZERO:
        return _check_trip_zero(active, tier, active_days, zero_volume_days)

    return _check_standard(active, tier, active_days, zero_volume_days)


def _check_trip_zero(
    active: list[DailyBar],
    tier: PriceTier,
    active_days: int,
    zero_volume_days: int,
) -> StabilityResult:
    """TRIP_ZERO stability: Tick Range Ratio <= threshold."""
    closes = [b.close for b in active]
    trr = compute_tick_range(closes)
    return StabilityResult(
        is_stable=trr <= TRIP_ZERO_MAX_TICK_LEVELS,
        tier=tier,
        active_days=active_days,
        zero_volume_days=zero_volume_days,
        tick_range=trr,
    )


def _get_thresholds(tier: PriceTier) -> StabilityThresholds:
    """Look up stability thresholds, mapping LOW_DUBS → DUBS."""
    if tier == PriceTier.LOW_DUBS:
        return STABILITY_THRESHOLDS[PriceTier.DUBS]
    return STABILITY_THRESHOLDS[tier]


def _check_standard(
    active: list[DailyBar],
    tier: PriceTier,
    active_days: int,
    zero_volume_days: int,
) -> StabilityResult:
    """Standard 4-metric stability check for TRIPS/LOW_DUBS/DUBS/PENNIES."""
    thresholds = _get_thresholds(tier)
    closes = [b.close for b in active]

    cv = compute_cv(closes)
    natr = compute_natr(active)
    bb_width = compute_bb_width(closes)
    prr = compute_price_range_ratio(closes)

    is_stable = (
        cv <= thresholds.cv_max
        and natr <= thresholds.natr_max
        and bb_width <= thresholds.bb_width_max
        and prr <= thresholds.price_range_ratio_max
    )

    return StabilityResult(
        is_stable=is_stable,
        tier=tier,
        active_days=active_days,
        zero_volume_days=zero_volume_days,
        cv=cv,
        natr=natr,
        bb_width=bb_width,
        price_range_ratio=prr,
    )


# ---------------------------------------------------------------------------
# Abnormal candle detection
# ---------------------------------------------------------------------------

def check_abnormal_candle(
    bar: DailyBar,
    tier: PriceTier,
    mean_close: Decimal,
    std_close: Decimal,
    mean_volume: int,
) -> AbnormalCandleResult:
    """Detect whether a daily bar is abnormal for its price tier.

    Uses dual threshold — flag if EITHER absolute move OR z-score triggers.
    Confirms directional move with body/range ratio check.

    Args:
        bar: Today's OHLCV bar.
        tier: Price tier of the symbol.
        mean_close: 30-day mean of closing prices (non-zero days).
        std_close: 30-day std dev of closing prices (non-zero days).
        mean_volume: Average volume over non-zero days.
    """
    thresholds: AbnormalCandleThresholds = ABNORMAL_CANDLE_THRESHOLDS.get(
        tier,
        # LOW_DUBS falls back to DUBS thresholds
        ABNORMAL_CANDLE_THRESHOLDS.get(PriceTier.DUBS, AbnormalCandleThresholds(
            abs_move_pct=Decimal("0.75"), zscore=Decimal("2.5"),
        )),
    )

    # Calculate absolute move percentage
    if tier == PriceTier.TRIP_ZERO:
        # TRIP_ZERO: abs_move is in ticks (integer price levels)
        tick_size = Decimal("0.0001")
        move_ticks = abs(bar.close - bar.open) / tick_size if tick_size > 0 else _ZERO
        abs_move_pct = move_ticks
        volume_spike = bar.volume > int(mean_volume * float(TRIP_ZERO_VOLUME_MULTIPLIER))
        abs_triggered = move_ticks >= thresholds.abs_move_pct and volume_spike
    else:
        abs_move_pct = (
            abs(bar.close - bar.open) / mean_close if mean_close > 0 else _ZERO
        )
        abs_triggered = abs_move_pct >= thresholds.abs_move_pct

    # Z-score check (not used for TRIP_ZERO)
    zscore = _ZERO
    zscore_triggered = False
    if tier != PriceTier.TRIP_ZERO and std_close > _ZERO:
        zscore = abs(bar.close - mean_close) / std_close
        zscore_triggered = zscore >= thresholds.zscore

    # Body-to-range ratio for directional confirmation
    bar_range = bar.high - bar.low
    body = abs(bar.close - bar.open)
    body_range_ratio = body / bar_range if bar_range > _ZERO else _ZERO
    directional = body_range_ratio >= CANDLE_BODY_RANGE_RATIO_MIN

    is_abnormal = abs_triggered or zscore_triggered

    return AbnormalCandleResult(
        is_abnormal=is_abnormal,
        abs_move_pct=abs_move_pct,
        zscore=zscore,
        body_range_ratio=body_range_ratio,
        directional=directional,
    )


# ---------------------------------------------------------------------------
# Convenience: compute mean/std for a close series (excludes zero-volume)
# ---------------------------------------------------------------------------

def compute_close_stats(bars: list[DailyBar]) -> tuple[Decimal, Decimal]:
    """Return (mean, std_dev) of closing prices from non-zero-volume bars."""
    active = _active_bars(bars)
    if not active:
        return _ZERO, _ZERO
    closes = [b.close for b in active]
    n = len(closes)
    mean = sum(closes) / n
    if n < 2:
        return mean, _ZERO
    variance = sum((c - mean) ** 2 for c in closes) / (n - _ONE)
    return mean, variance.sqrt()


def compute_mean_volume(bars: list[DailyBar]) -> int:
    """Return mean volume from non-zero-volume bars."""
    active = _active_bars(bars)
    if not active:
        return 0
    return sum(b.volume for b in active) // len(active)
