"""OTC Health Index (OHI) — market condition gate for new entries.

Composite 0-100 score from 6 components. Determines whether
new entries are allowed and at what position sizing.
"""

from dataclasses import dataclass
from decimal import Decimal

import structlog

from config.constants import (
    OHI_NEUTRAL_LOW,
    OHI_STRONG,
    OHI_WEIGHT_ADV_DECLINE,
    OHI_WEIGHT_DOLLAR_VOLUME,
    OHI_WEIGHT_HIGHS_LOWS,
    OHI_WEIGHT_MOVERS,
    OHI_WEIGHT_SECTOR,
    OHI_WEIGHT_SPY,
)

logger = structlog.get_logger(__name__)

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_HALF = Decimal("0.5")
_ONE = Decimal("1")


@dataclass(frozen=True)
class OHIResult:
    """OTC Health Index computation result."""

    score: Decimal          # 0-100 composite
    regime: str             # "STRONG" | "NEUTRAL" | "WEAK"
    sizing_factor: Decimal  # 1.0 | 0.5 | 0
    allow_new_entries: bool
    components: dict[str, Decimal]


class MarketHealthAnalyzer:
    """Computes OTC Health Index from 6 market-wide inputs.

    Each component is a raw value 0-100 representing that signal's
    contribution. The composite is a weighted sum.

    Components:
        - adv_decline_score: OTC advance/decline ratio (25%)
        - dollar_volume_score: total OTC $ volume vs 20-day avg (20%)
        - movers_score: count of 100%+ daily movers (15%)
        - spy_score: SPY direction (15%)
        - sector_score: active sector theme presence (15%)
        - highs_lows_score: net new 52-week highs minus lows (10%)
    """

    def __init__(self) -> None:
        self._last_result: OHIResult | None = None

    @property
    def last_result(self) -> OHIResult | None:
        return self._last_result

    def compute(
        self,
        adv_decline_score: Decimal,
        dollar_volume_score: Decimal,
        movers_score: Decimal,
        spy_score: Decimal,
        sector_score: Decimal,
        highs_lows_score: Decimal,
    ) -> OHIResult:
        """Compute OHI from 6 component scores (each 0-100)."""
        # Clamp inputs to [0, 100]
        components = {
            "adv_decline": _clamp(adv_decline_score),
            "dollar_volume": _clamp(dollar_volume_score),
            "movers": _clamp(movers_score),
            "spy": _clamp(spy_score),
            "sector": _clamp(sector_score),
            "highs_lows": _clamp(highs_lows_score),
        }

        score = (
            components["adv_decline"] * OHI_WEIGHT_ADV_DECLINE
            + components["dollar_volume"] * OHI_WEIGHT_DOLLAR_VOLUME
            + components["movers"] * OHI_WEIGHT_MOVERS
            + components["spy"] * OHI_WEIGHT_SPY
            + components["sector"] * OHI_WEIGHT_SECTOR
            + components["highs_lows"] * OHI_WEIGHT_HIGHS_LOWS
        )

        # Determine regime
        if score >= Decimal(str(OHI_STRONG)):
            regime = "STRONG"
            sizing_factor = _ONE
            allow = True
        elif score >= Decimal(str(OHI_NEUTRAL_LOW)):
            regime = "NEUTRAL"
            sizing_factor = _HALF
            allow = True
        else:
            regime = "WEAK"
            sizing_factor = _ZERO
            allow = False

        result = OHIResult(
            score=score,
            regime=regime,
            sizing_factor=sizing_factor,
            allow_new_entries=allow,
            components=components,
        )
        self._last_result = result

        logger.info(
            "ohi_computed",
            score=str(score),
            regime=regime,
            sizing_factor=str(sizing_factor),
        )

        return result


def _clamp(value: Decimal) -> Decimal:
    """Clamp a value to [0, 100]."""
    if value < _ZERO:
        return _ZERO
    if value > _HUNDRED:
        return _HUNDRED
    return value
