"""OTC candidate screener — filters by price tier, stability, and volume.

Subscribes to MarketDataEvent, evaluates candidates against tier-specific
thresholds, and publishes ScannerHitEvent when all filters pass.
"""

from decimal import Decimal

import structlog

from config.constants import (
    ZERO_VOLUME_WARNING_THRESHOLD,
    get_tier,
)
from src.core.event_bus import EventBus
from src.core.events import MarketDataEvent, ScannerHitEvent
from src.scanner.stability import (
    DailyBar,
    StabilityResult,
    check_abnormal_candle,
    check_stability,
    compute_close_stats,
    compute_mean_volume,
)

logger = structlog.get_logger(__name__)

_DEFAULT_WINDOW = 30  # 30-day lookback for stability
_ZERO = Decimal("0")


class Screener:
    """Filters OTC candidates by price, stability, and volume.

    Lifecycle:
        1. Construct with an EventBus.
        2. Call ``start()`` to subscribe to MarketDataEvent.
        3. Feed historical bars via ``add_daily_bar()`` for each symbol.
        4. Incoming MarketDataEvent triggers evaluation.
        5. Passing candidates get a ScannerHitEvent published.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._bars: dict[str, list[DailyBar]] = {}
        self._last_result: dict[str, StabilityResult] = {}
        self._rejected: set[str] = set()

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        """Subscribe to market data events on the bus."""
        self._event_bus.subscribe(MarketDataEvent, self._on_market_data)
        logger.info("screener_started")

    # ── Historical bar management ────────────────────────────────

    def add_daily_bar(self, symbol: str, bar: DailyBar) -> None:
        """Append a daily OHLCV bar to the symbol's history.

        Maintains a rolling window of ``_DEFAULT_WINDOW`` bars.
        """
        if symbol not in self._bars:
            self._bars[symbol] = []
        self._bars[symbol].append(bar)
        # Trim to rolling window
        if len(self._bars[symbol]) > _DEFAULT_WINDOW:
            self._bars[symbol] = self._bars[symbol][-_DEFAULT_WINDOW:]

    def get_bars(self, symbol: str) -> list[DailyBar]:
        """Return stored bars for a symbol (empty list if none)."""
        return list(self._bars.get(symbol, []))

    def get_last_result(self, symbol: str) -> StabilityResult | None:
        """Return the most recent stability result for a symbol."""
        return self._last_result.get(symbol)

    # ── Evaluation ───────────────────────────────────────────────

    async def evaluate(self, symbol: str, price: Decimal, volume: int) -> bool:
        """Evaluate a symbol against all scanner filters.

        Returns True if the symbol passes and a ScannerHitEvent was published.
        """
        # Skip previously rejected symbols
        if symbol in self._rejected:
            return False

        # 1) Price tier check
        tier = get_tier(price)
        if tier is None:
            logger.debug("screener_skip_no_tier", symbol=symbol, price=str(price))
            return False

        # 2) Sufficient historical data
        bars = self._bars.get(symbol, [])
        if not bars:
            logger.debug("screener_skip_no_bars", symbol=symbol)
            return False

        # 3) Stability check
        result = check_stability(bars, tier)
        self._last_result[symbol] = result

        if not result.is_stable:
            logger.debug(
                "screener_unstable",
                symbol=symbol,
                tier=tier.value,
                active_days=result.active_days,
                cv=str(result.cv) if result.cv is not None else None,
                natr=str(result.natr) if result.natr is not None else None,
            )
            return False

        # 4) Zero-volume day warning (non-blocking, just logged)
        if result.zero_volume_days > ZERO_VOLUME_WARNING_THRESHOLD:
            logger.warning(
                "screener_low_activity",
                symbol=symbol,
                zero_days=result.zero_volume_days,
            )

        # 5) Abnormal candle check on latest bar
        latest_bar = bars[-1]
        mean_close, std_close = compute_close_stats(bars)
        mean_vol = compute_mean_volume(bars)
        candle_result = check_abnormal_candle(
            latest_bar, tier, mean_close, std_close, mean_vol
        )
        if candle_result.is_abnormal:
            logger.info(
                "screener_abnormal_candle",
                symbol=symbol,
                tier=tier.value,
                abs_move=str(candle_result.abs_move_pct),
                zscore=str(candle_result.zscore),
                directional=candle_result.directional,
            )
            return False

        # All filters passed → publish ScannerHitEvent
        event = ScannerHitEvent(
            ticker=symbol,
            price_tier=tier.value,
            price=price,
            volume=volume,
        )
        await self._event_bus.publish(event)
        logger.info(
            "scanner_hit",
            symbol=symbol,
            tier=tier.value,
            price=str(price),
            volume=volume,
            active_days=result.active_days,
        )
        return True

    def reject(self, symbol: str, reason: str) -> None:
        """Manually reject a symbol (skipped on future evaluations)."""
        self._rejected.add(symbol)
        logger.info("screener_rejected", symbol=symbol, reason=reason)

    def unreject(self, symbol: str) -> None:
        """Remove a symbol from the rejected set."""
        self._rejected.discard(symbol)

    # ── Event handler ────────────────────────────────────────────

    async def _on_market_data(self, event: MarketDataEvent) -> None:
        """Handle incoming market data — run evaluation."""
        await self.evaluate(event.ticker, event.price, event.volume)
