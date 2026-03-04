"""L2 (Level 2) analyzer — imbalance ratio, MM classification, wall detection.

Subscribes to L2UpdateEvent, maintains per-symbol state, and exposes
analysis results for the ATM scorer and dilution sentinel.
"""

from dataclasses import dataclass, field
from decimal import Decimal

import structlog

from config.constants import (
    L2_IMBALANCE_FAVORABLE,
    L2_IMBALANCE_STRONG,
    MM_BAD,
    WALL_RATIO_SIGNIFICANT,
    WALL_SCORE_MAX,
)
from src.core.event_bus import EventBus
from src.core.events import L2UpdateEvent

logger = structlog.get_logger(__name__)

_ZERO = Decimal("0")
_TEN = Decimal("10")


@dataclass
class WallInfo:
    """A detected wall at a specific price level."""

    price: Decimal
    size: int
    mm_id: str
    side: str  # "bid" | "ask"
    wall_ratio: Decimal  # size / ADV
    wall_score: Decimal  # min(10, (size/ADV) * 10)


@dataclass
class L2Analysis:
    """Snapshot of L2 analysis for a single symbol."""

    ticker: str
    imbalance_ratio: Decimal
    imbalance_label: str  # "STRONG" | "FAVORABLE" | "INSUFFICIENT"
    total_bid_shares: int
    total_ask_shares: int
    has_bad_mm_on_ask: bool
    bad_mm_list: list[str] = field(default_factory=list)
    bid_walls: list[WallInfo] = field(default_factory=list)
    ask_walls: list[WallInfo] = field(default_factory=list)
    bid_mm_ids: list[str] = field(default_factory=list)
    ask_mm_ids: list[str] = field(default_factory=list)


class L2Analyzer:
    """Analyzes L2 depth data for imbalance, MM presence, and walls.

    Lifecycle:
        1. Construct with EventBus.
        2. Call ``start()`` to subscribe to L2UpdateEvent.
        3. Optionally set ADV per symbol via ``set_adv()``.
        4. Each L2 update recalculates analysis for that symbol.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._results: dict[str, L2Analysis] = {}
        self._adv: dict[str, int] = {}  # average daily volume per symbol

    def start(self) -> None:
        self._event_bus.subscribe(L2UpdateEvent, self._on_l2_update)
        logger.info("l2_analyzer_started")

    def set_adv(self, symbol: str, adv: int) -> None:
        """Set average daily volume for wall ratio calculations."""
        self._adv[symbol] = adv

    def get_result(self, symbol: str) -> L2Analysis | None:
        return self._results.get(symbol)

    async def _on_l2_update(self, event: L2UpdateEvent) -> None:
        result = self.analyze(event)
        self._results[event.ticker] = result

    def analyze(self, event: L2UpdateEvent) -> L2Analysis:
        """Compute L2 analysis from a single L2UpdateEvent."""
        ticker = event.ticker

        # Sum bid/ask shares
        total_bid = sum(size for _, size, _ in event.bid_levels)
        total_ask = sum(size for _, size, _ in event.ask_levels)

        # Imbalance ratio
        if total_ask > 0:
            ratio = Decimal(str(total_bid)) / Decimal(str(total_ask))
        else:
            ratio = Decimal("Infinity") if total_bid > 0 else _ZERO

        if ratio >= L2_IMBALANCE_STRONG:
            label = "STRONG"
        elif ratio >= L2_IMBALANCE_FAVORABLE:
            label = "FAVORABLE"
        else:
            label = "INSUFFICIENT"

        # MM classification
        bid_mm_ids = [mm for _, _, mm in event.bid_levels if mm]
        ask_mm_ids = [mm for _, _, mm in event.ask_levels if mm]
        bad_on_ask = [mm for mm in ask_mm_ids if mm.upper().strip() in MM_BAD]

        # Wall detection
        adv = self._adv.get(ticker, 0)
        bid_walls = self._detect_walls(event.bid_levels, "bid", adv)
        ask_walls = self._detect_walls(event.ask_levels, "ask", adv)

        return L2Analysis(
            ticker=ticker,
            imbalance_ratio=ratio,
            imbalance_label=label,
            total_bid_shares=total_bid,
            total_ask_shares=total_ask,
            has_bad_mm_on_ask=len(bad_on_ask) > 0,
            bad_mm_list=bad_on_ask,
            bid_walls=bid_walls,
            ask_walls=ask_walls,
            bid_mm_ids=bid_mm_ids,
            ask_mm_ids=ask_mm_ids,
        )

    def _detect_walls(
        self,
        levels: tuple[tuple[Decimal, int, str], ...],
        side: str,
        adv: int,
    ) -> list[WallInfo]:
        """Detect walls in a set of price levels."""
        if adv <= 0:
            return []
        walls: list[WallInfo] = []
        for price, size, mm_id in levels:
            wall_ratio = Decimal(str(size)) / Decimal(str(adv))
            if wall_ratio >= WALL_RATIO_SIGNIFICANT:
                wall_score = min(WALL_SCORE_MAX, wall_ratio * _TEN)
                walls.append(WallInfo(
                    price=price,
                    size=size,
                    mm_id=mm_id,
                    side=side,
                    wall_ratio=wall_ratio,
                    wall_score=wall_score,
                ))
        return walls
