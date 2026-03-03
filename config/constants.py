"""All thresholds, enums, and constants. Zero magic numbers in application code."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

# ---------------------------------------------------------------------------
# Price Tiers
# ---------------------------------------------------------------------------

class PriceTier(StrEnum):
    TRIP_ZERO = "TRIP_ZERO"
    TRIPS = "TRIPS"
    LOW_DUBS = "LOW_DUBS"
    DUBS = "DUBS"
    PENNIES = "PENNIES"


@dataclass(frozen=True)
class TierRange:
    low: Decimal
    high: Decimal


TIER_RANGES: dict[PriceTier, TierRange] = {
    PriceTier.TRIP_ZERO: TierRange(Decimal("0.0001"), Decimal("0.0005")),
    PriceTier.TRIPS: TierRange(Decimal("0.0001"), Decimal("0.0009")),
    PriceTier.LOW_DUBS: TierRange(Decimal("0.001"), Decimal("0.003")),
    PriceTier.DUBS: TierRange(Decimal("0.001"), Decimal("0.0099")),
    PriceTier.PENNIES: TierRange(Decimal("0.01"), Decimal("0.03")),
}


def get_tier(price: Decimal) -> PriceTier | None:
    """Return the most specific tier for a given price, or None."""
    if Decimal("0.0001") <= price <= Decimal("0.0005"):
        return PriceTier.TRIP_ZERO
    if Decimal("0.0001") <= price <= Decimal("0.0009"):
        return PriceTier.TRIPS
    if Decimal("0.001") <= price <= Decimal("0.003"):
        return PriceTier.LOW_DUBS
    if Decimal("0.001") <= price <= Decimal("0.0099"):
        return PriceTier.DUBS
    if Decimal("0.01") <= price <= Decimal("0.03"):
        return PriceTier.PENNIES
    return None


# ---------------------------------------------------------------------------
# Stability Thresholds (per tier)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StabilityThresholds:
    cv_max: Decimal
    natr_max: Decimal
    bb_width_max: Decimal
    price_range_ratio_max: Decimal


STABILITY_THRESHOLDS: dict[PriceTier, StabilityThresholds] = {
    PriceTier.TRIPS: StabilityThresholds(
        cv_max=Decimal("0.40"),
        natr_max=Decimal("0.40"),
        bb_width_max=Decimal("0.50"),
        price_range_ratio_max=Decimal("0.50"),
    ),
    PriceTier.DUBS: StabilityThresholds(
        cv_max=Decimal("0.25"),
        natr_max=Decimal("0.25"),
        bb_width_max=Decimal("0.50"),
        price_range_ratio_max=Decimal("0.50"),
    ),
    PriceTier.PENNIES: StabilityThresholds(
        cv_max=Decimal("0.15"),
        natr_max=Decimal("0.25"),
        bb_width_max=Decimal("0.50"),
        price_range_ratio_max=Decimal("0.50"),
    ),
}

# TRIP_ZERO uses Tick Range Ratio instead of the four-metric system.
TRIP_ZERO_MAX_TICK_LEVELS: int = 3

# Minimum non-zero-volume trading days in 30-day window.
MIN_ACTIVE_TRADING_DAYS: int = 15


# ---------------------------------------------------------------------------
# Abnormal Candle Thresholds (per tier)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AbnormalCandleThresholds:
    abs_move_pct: Decimal
    zscore: Decimal


ABNORMAL_CANDLE_THRESHOLDS: dict[PriceTier, AbnormalCandleThresholds] = {
    PriceTier.TRIP_ZERO: AbnormalCandleThresholds(
        abs_move_pct=Decimal("3"),  # 3 ticks
        zscore=Decimal("0"),        # N/A — tick-based only
    ),
    PriceTier.TRIPS: AbnormalCandleThresholds(
        abs_move_pct=Decimal("1.50"),
        zscore=Decimal("3.0"),
    ),
    PriceTier.DUBS: AbnormalCandleThresholds(
        abs_move_pct=Decimal("0.75"),
        zscore=Decimal("2.5"),
    ),
    PriceTier.PENNIES: AbnormalCandleThresholds(
        abs_move_pct=Decimal("0.30"),
        zscore=Decimal("2.5"),
    ),
}

CANDLE_BODY_RANGE_RATIO_MIN: Decimal = Decimal("0.60")
TRIP_ZERO_VOLUME_MULTIPLIER: Decimal = Decimal("1.5")


# ---------------------------------------------------------------------------
# L2 Imbalance
# ---------------------------------------------------------------------------

L2_IMBALANCE_FAVORABLE: Decimal = Decimal("3.0")
L2_IMBALANCE_STRONG: Decimal = Decimal("5.0")


# ---------------------------------------------------------------------------
# Wall Detection
# ---------------------------------------------------------------------------

WALL_RATIO_SIGNIFICANT: Decimal = Decimal("0.05")
WALL_RATIO_MAJOR: Decimal = Decimal("0.10")
WALL_RATIO_DOMINANT: Decimal = Decimal("0.25")
WALL_SCORE_STRONG: Decimal = Decimal("5")
WALL_SCORE_DOMINANT: Decimal = Decimal("8")
WALL_SCORE_MAX: Decimal = Decimal("10")
WALL_BREAKING_VOLUME_PCT: Decimal = Decimal("0.50")


# ---------------------------------------------------------------------------
# Refresh Detection FSM
# ---------------------------------------------------------------------------

REFRESH_SIZE_TOLERANCE: Decimal = Decimal("0.20")
REFRESH_TIMEOUT_ALGO_SEC: int = 30
REFRESH_TIMEOUT_MANUAL_SEC: int = 60
REFRESH_MIN_CONSECUTIVE: int = 3
REFRESH_INTENSITY_SIGNIFICANT: Decimal = Decimal("0.5")
FILL_TO_DISPLAY_RATIO_CONFIRM: Decimal = Decimal("5.0")


# ---------------------------------------------------------------------------
# Market Maker Classification
# ---------------------------------------------------------------------------

class MMClassification(StrEnum):
    BAD = "BAD"
    RETAIL = "RETAIL"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


MM_BAD: frozenset[str] = frozenset({
    "MAXM", "GLED", "CFGN", "PAUL", "JANE", "BBAR", "BLAS",
    "ALPS", "STXG", "AEXG", "VFIN", "VERT", "BMAK",
})

MM_RETAIL: frozenset[str] = frozenset({
    "ETRF", "CSTI", "GTSM", "NITE",
})

MM_NEUTRAL: frozenset[str] = frozenset({
    "OTCN", "OTCX", "CDEL", "INTL", "VIRT",
})


def classify_mm(mm_id: str) -> MMClassification:
    """Classify a market maker by MPID."""
    mpid = mm_id.upper().strip()
    if mpid in MM_BAD:
        return MMClassification.BAD
    if mpid in MM_RETAIL:
        return MMClassification.RETAIL
    if mpid in MM_NEUTRAL:
        return MMClassification.NEUTRAL
    return MMClassification.UNKNOWN


# ---------------------------------------------------------------------------
# Dilution Scoring
# ---------------------------------------------------------------------------

DILUTION_POINTS_BAD_MM_ASK: int = 4
DILUTION_POINTS_VOLUME_SPIKE_FLAT: int = 3
DILUTION_POINTS_BID_EROSION: int = 2
DILUTION_POINTS_BLOCK_TRADES_BID: int = 2
DILUTION_POINTS_SHARES_INCREASE: int = 3
DILUTION_POINTS_RATIO_DROP: int = 1

DILUTION_CLEAR_MAX: int = 2
DILUTION_WARNING_MAX: int = 4
DILUTION_HIGH_ALERT_MAX: int = 6
DILUTION_EXIT_TRIGGER: int = 3


# ---------------------------------------------------------------------------
# Volume Analysis
# ---------------------------------------------------------------------------

VOLUME_ZSCORE_NOTABLE: Decimal = Decimal("2.0")
VOLUME_ZSCORE_SIGNIFICANT: Decimal = Decimal("3.0")
VOLUME_ZSCORE_EXTREME: Decimal = Decimal("5.0")

RVOL_SIGNIFICANT: Decimal = Decimal("2.0")
RVOL_EXTREME: Decimal = Decimal("5.0")

VOLUME_LOOKBACK_DAYS: int = 20
VOLUME_LOOKBACK_EXTENDED: int = 50
ZERO_VOLUME_WARNING_THRESHOLD: int = 10


# ---------------------------------------------------------------------------
# Risk Constants
# ---------------------------------------------------------------------------

MAX_HOLD_HOURS_TRIPS_INTRADAY: int = 4
MAX_HOLD_DAYS_TRIPS_OVERNIGHT: int = 2
MAX_HOLD_DAYS_DUBS: int = 2
MAX_HOLD_DAYS_PENNIES: int = 5

BID_COLLAPSE_EXIT_PCT: Decimal = Decimal("0.30")
VOLATILITY_STOP_ATR_MULTIPLIER: Decimal = Decimal("2.0")


# ---------------------------------------------------------------------------
# OTC Health Index (OHI)
# ---------------------------------------------------------------------------

OHI_STRONG: int = 65
OHI_NEUTRAL_LOW: int = 40

OHI_WEIGHT_ADV_DECLINE: Decimal = Decimal("0.25")
OHI_WEIGHT_DOLLAR_VOLUME: Decimal = Decimal("0.20")
OHI_WEIGHT_MOVERS: Decimal = Decimal("0.15")
OHI_WEIGHT_SPY: Decimal = Decimal("0.15")
OHI_WEIGHT_SECTOR: Decimal = Decimal("0.15")
OHI_WEIGHT_HIGHS_LOWS: Decimal = Decimal("0.10")


# ---------------------------------------------------------------------------
# ATM Probability Scorer Weights (max score per component)
# ---------------------------------------------------------------------------

ATM_WEIGHT_STABILITY: int = 15
ATM_WEIGHT_L2_IMBALANCE: int = 20
ATM_WEIGHT_NO_BAD_MM: int = 15
ATM_WEIGHT_NO_VOLUME_ANOMALY: int = 10
ATM_WEIGHT_CONSISTENT_VOLUME: int = 10
ATM_WEIGHT_BID_SUPPORT: int = 10
ATM_WEIGHT_TS_RATIO: int = 10
ATM_WEIGHT_DILUTION_CLEAR: int = 10

ATM_MIN_WATCHLIST: int = 70
ATM_MIN_TRADE: int = 80


# ---------------------------------------------------------------------------
# Prop Bid Detection
# ---------------------------------------------------------------------------

PROP_BID_FLAG_THRESHOLD: int = 6
PROP_BID_MAX_SCORE: int = 18
PROP_BID_EXECUTION_RATIO: Decimal = Decimal("10.0")
PROP_BID_CANCEL_RATE: Decimal = Decimal("0.80")
