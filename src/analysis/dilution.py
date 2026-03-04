"""Dilution sentinel — composite score (0-10) from multiple signal sources.

Aggregates signals from L2, volume, and T&S analyzers into a single
dilution risk score. Publishes DilutionAlertEvent when score >= WARNING.
"""

from dataclasses import dataclass
from decimal import Decimal

import structlog

from config.constants import (
    DILUTION_CLEAR_MAX,
    DILUTION_EXIT_TRIGGER,
    DILUTION_HIGH_ALERT_MAX,
    DILUTION_POINTS_BAD_MM_ASK,
    DILUTION_POINTS_BID_EROSION,
    DILUTION_POINTS_BLOCK_TRADES_BID,
    DILUTION_POINTS_RATIO_DROP,
    DILUTION_POINTS_VOLUME_SPIKE_FLAT,
    DILUTION_WARNING_MAX,
    L2_IMBALANCE_FAVORABLE,
    VOLUME_ZSCORE_SIGNIFICANT,
)
from src.analysis.level2 import L2Analyzer
from src.analysis.time_sales import TSAnalyzer
from src.analysis.volume import VolumeAnalyzer
from src.core.event_bus import EventBus
from src.core.events import DilutionAlertEvent

logger = structlog.get_logger(__name__)

_ZERO = Decimal("0")


@dataclass(frozen=True)
class DilutionAnalysis:
    """Snapshot of dilution analysis for a single symbol."""

    ticker: str
    score: int
    severity: str  # "CLEAR" | "WARNING" | "HIGH_ALERT" | "CRITICAL"
    should_exit: bool
    signals: tuple[str, ...]
    has_bad_mm: bool


class DilutionSentinel:
    """Composite dilution risk scoring from multiple analyzers.

    Queries L2Analyzer, VolumeAnalyzer, and TSAnalyzer results to build
    a dilution score. Does not subscribe to raw events directly.

    Lifecycle:
        1. Construct with EventBus and the three analyzer instances.
        2. Call ``evaluate(symbol)`` to compute/refresh the dilution score.
        3. Publishes DilutionAlertEvent for WARNING+ scores.
    """

    def __init__(
        self,
        event_bus: EventBus,
        l2_analyzer: L2Analyzer,
        volume_analyzer: VolumeAnalyzer,
        ts_analyzer: TSAnalyzer,
    ) -> None:
        self._event_bus = event_bus
        self._l2 = l2_analyzer
        self._volume = volume_analyzer
        self._ts = ts_analyzer
        self._results: dict[str, DilutionAnalysis] = {}
        self._prev_imbalance: dict[str, Decimal] = {}

    def get_result(self, symbol: str) -> DilutionAnalysis | None:
        return self._results.get(symbol)

    async def evaluate(self, symbol: str) -> DilutionAnalysis:
        """Compute dilution score for a symbol from all analyzer results."""
        score = 0
        signals: list[str] = []
        has_bad_mm = False

        # ── Signal 1: Bad MM on Ask (+4) ─────────────────────────
        l2 = self._l2.get_result(symbol)
        if l2 and l2.has_bad_mm_on_ask:
            score += DILUTION_POINTS_BAD_MM_ASK
            has_bad_mm = True
            signals.append(f"Bad MM on ask: {', '.join(l2.bad_mm_list)}")

        # ── Signal 2: Volume spike with flat/down price (+3) ─────
        vol = self._volume.get_result(symbol)
        if vol and vol.zscore >= VOLUME_ZSCORE_SIGNIFICANT:
            # Volume is spiking — check if price isn't rising
            # (volume spike + no price appreciation = potential dumping)
            signals.append(
                f"Volume spike: z={vol.zscore:.1f}, RVOL={vol.rvol:.1f}"
            )
            score += DILUTION_POINTS_VOLUME_SPIKE_FLAT

        # ── Signal 3: Bid erosion — imbalance ratio dropping (+2) ─
        if l2:
            prev = self._prev_imbalance.get(symbol)
            if (
                prev is not None
                and prev > _ZERO
                and l2.imbalance_ratio < prev * Decimal("0.7")
            ):
                score += DILUTION_POINTS_BID_EROSION
                signals.append(
                    f"Bid erosion: ratio {prev:.1f} -> {l2.imbalance_ratio:.1f}"
                )
            self._prev_imbalance[symbol] = l2.imbalance_ratio

        # ── Signal 4: Block trades on bid side (+2) ──────────────
        ts = self._ts.get_result(symbol)
        if ts:
            bid_blocks = [b for b in ts.block_trades if b.side == "bid"]
            if bid_blocks:
                score += DILUTION_POINTS_BLOCK_TRADES_BID
                total_block_size = sum(b.total_size for b in bid_blocks)
                signals.append(
                    f"Block trades on bid: {len(bid_blocks)} blocks, "
                    f"{total_block_size:,} shares"
                )

        # ── Signal 5: Buyer/seller ratio below 2:1 (+1) ─────────
        if ts and ts.buy_sell_ratio < Decimal("2") and ts.total_trades > 0:
            score += DILUTION_POINTS_RATIO_DROP
            signals.append(f"Buy/sell ratio low: {ts.buy_sell_ratio:.2f}")

        # ── Signal 6: Imbalance below favorable (+1 additional) ──
        if (
            l2
            and l2.imbalance_ratio < L2_IMBALANCE_FAVORABLE
            and l2.total_ask_shares > 0
            and "Bid erosion" not in str(signals)
        ):
            signals.append(
                f"L2 imbalance insufficient: {l2.imbalance_ratio:.1f}"
            )

        # Cap at 10
        score = min(score, 10)

        # Classify severity
        severity = self._classify_severity(score)
        should_exit = score >= DILUTION_EXIT_TRIGGER

        result = DilutionAnalysis(
            ticker=symbol,
            score=score,
            severity=severity,
            should_exit=should_exit,
            signals=tuple(signals),
            has_bad_mm=has_bad_mm,
        )
        self._results[symbol] = result

        # Publish alert for WARNING+
        if severity != "CLEAR":
            alert = DilutionAlertEvent(
                ticker=symbol,
                dilution_score=score,
                severity=severity,
                signals=tuple(signals),
                message=f"Dilution score {score}/10 ({severity}): {'; '.join(signals)}",
            )
            await self._event_bus.publish(alert)
            logger.warning(
                "dilution_alert",
                ticker=symbol,
                score=score,
                severity=severity,
                signals=signals,
            )

        return result

    @staticmethod
    def _classify_severity(score: int) -> str:
        if score <= DILUTION_CLEAR_MAX:
            return "CLEAR"
        if score <= DILUTION_WARNING_MAX:
            return "WARNING"
        if score <= DILUTION_HIGH_ALERT_MAX:
            return "HIGH_ALERT"
        return "CRITICAL"
