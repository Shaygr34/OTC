"""Volume analyzer — modified z-score, RVOL, anomaly flagging.

Subscribes to MarketDataEvent, maintains a per-symbol volume history,
and computes anomaly metrics on each update.
"""

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

import structlog

from config.constants import (
    RVOL_EXTREME,
    RVOL_SIGNIFICANT,
    VOLUME_LOOKBACK_DAYS,
    VOLUME_ZSCORE_EXTREME,
    VOLUME_ZSCORE_NOTABLE,
    VOLUME_ZSCORE_SIGNIFICANT,
    ZERO_VOLUME_WARNING_THRESHOLD,
)
from src.core.event_bus import EventBus
from src.core.events import AlertEvent, MarketDataEvent

logger = structlog.get_logger(__name__)

_ZERO = Decimal("0")
_ONE = Decimal("1")


@dataclass(frozen=True)
class VolumeAnalysis:
    """Snapshot of volume analysis for a single symbol."""

    ticker: str
    current_volume: int
    mean_volume: Decimal
    std_volume: Decimal
    zscore: Decimal
    rvol: Decimal
    anomaly_level: str  # "NORMAL" | "NOTABLE" | "SIGNIFICANT" | "EXTREME"
    active_days: int
    zero_volume_days: int
    low_activity_warning: bool


class VolumeAnalyzer:
    """Analyzes volume patterns for anomaly detection.

    Lifecycle:
        1. Construct with EventBus.
        2. Call ``start()`` to subscribe to MarketDataEvent.
        3. Seed history via ``add_volume(symbol, volume)`` for each past day.
        4. Each MarketDataEvent triggers re-analysis for that symbol.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._history: dict[str, deque[int]] = {}
        self._results: dict[str, VolumeAnalysis] = {}

    def start(self) -> None:
        self._event_bus.subscribe(MarketDataEvent, self._on_market_data)
        logger.info("volume_analyzer_started")

    def add_volume(self, symbol: str, volume: int) -> None:
        """Append a daily volume figure to the symbol's history."""
        if symbol not in self._history:
            self._history[symbol] = deque(maxlen=VOLUME_LOOKBACK_DAYS)
        self._history[symbol].append(volume)

    def get_result(self, symbol: str) -> VolumeAnalysis | None:
        return self._results.get(symbol)

    async def _on_market_data(self, event: MarketDataEvent) -> None:
        result = self.analyze(event.ticker, event.volume)
        self._results[event.ticker] = result

        # Publish alert for significant+ anomalies
        if result.anomaly_level in ("SIGNIFICANT", "EXTREME"):
            alert = AlertEvent(
                ticker=event.ticker,
                alert_type="VOLUME_ANOMALY",
                severity="HIGH" if result.anomaly_level == "EXTREME" else "WARNING",
                message=(
                    f"Volume anomaly: z={result.zscore:.1f}, "
                    f"RVOL={result.rvol:.1f}, vol={result.current_volume}"
                ),
            )
            await self._event_bus.publish(alert)

    def analyze(self, symbol: str, current_volume: int) -> VolumeAnalysis:
        """Compute volume analysis for a symbol given today's volume."""
        history = list(self._history.get(symbol, []))

        # Separate active (non-zero) and zero-volume days
        active_vols = [v for v in history if v > 0]
        active_days = len(active_vols)
        zero_volume_days = len(history) - active_days

        low_activity = zero_volume_days > ZERO_VOLUME_WARNING_THRESHOLD

        if active_days < 2:
            return VolumeAnalysis(
                ticker=symbol,
                current_volume=current_volume,
                mean_volume=_ZERO,
                std_volume=_ZERO,
                zscore=_ZERO,
                rvol=_ZERO,
                anomaly_level="NORMAL",
                active_days=active_days,
                zero_volume_days=zero_volume_days,
                low_activity_warning=low_activity,
            )

        # Mean and std on non-zero days only
        n = Decimal(str(active_days))
        dec_vols = [Decimal(str(v)) for v in active_vols]
        mean = sum(dec_vols) / n
        variance = sum((v - mean) ** 2 for v in dec_vols) / (n - _ONE)
        std = variance.sqrt()

        # Modified z-score
        zscore = (Decimal(str(current_volume)) - mean) / std if std > _ZERO else _ZERO

        # RVOL (relative volume)
        rvol = Decimal(str(current_volume)) / mean if mean > _ZERO else _ZERO

        # Classify anomaly
        if zscore >= VOLUME_ZSCORE_EXTREME or rvol >= RVOL_EXTREME:
            level = "EXTREME"
        elif zscore >= VOLUME_ZSCORE_SIGNIFICANT or rvol >= RVOL_SIGNIFICANT:
            level = "SIGNIFICANT"
        elif zscore >= VOLUME_ZSCORE_NOTABLE:
            level = "NOTABLE"
        else:
            level = "NORMAL"

        return VolumeAnalysis(
            ticker=symbol,
            current_volume=current_volume,
            mean_volume=mean,
            std_volume=std,
            zscore=zscore,
            rvol=rvol,
            anomaly_level=level,
            active_days=active_days,
            zero_volume_days=zero_volume_days,
            low_activity_warning=low_activity,
        )
