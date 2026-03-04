"""Time & Sales analyzer — bid/ask classifier, block and cross trade detection.

Subscribes to TradeEvent, maintains per-symbol trade history, and computes
buy/sell ratio plus pattern detection.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import structlog

from src.core.event_bus import EventBus
from src.core.events import TradeEvent

logger = structlog.get_logger(__name__)

_ZERO = Decimal("0")
_ONE = Decimal("1")
_MAX_HISTORY = 500  # max trades to keep per symbol
_BLOCK_TIME_WINDOW_SEC = 1  # trades within 1 second at same price = block candidate
_BLOCK_MIN_TRADES = 3  # minimum fills to flag as a block


@dataclass(frozen=True)
class BlockTrade:
    """A detected block trade pattern (multiple fills at same price/time)."""

    price: Decimal
    total_size: int
    fill_count: int
    side: str
    timestamp: datetime


@dataclass(frozen=True)
class TSAnalysis:
    """Snapshot of Time & Sales analysis for a single symbol."""

    ticker: str
    total_trades: int
    bid_hits: int  # trades at bid (sells)
    ask_hits: int  # trades at ask (buys)
    unknown_trades: int
    buy_sell_ratio: Decimal  # ask_hits / bid_hits
    is_bullish: bool  # ratio > 1.0
    block_trades: tuple[BlockTrade, ...] = ()
    recent_mm_ids: tuple[str, ...] = ()


class TSAnalyzer:
    """Analyzes Time & Sales data for trade classification and patterns.

    Lifecycle:
        1. Construct with EventBus.
        2. Call ``start()`` to subscribe to TradeEvent.
        3. Each trade is classified and running stats updated.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._trades: dict[str, deque[TradeEvent]] = {}
        self._results: dict[str, TSAnalysis] = {}

    def start(self) -> None:
        self._event_bus.subscribe(TradeEvent, self._on_trade)
        logger.info("ts_analyzer_started")

    def get_result(self, symbol: str) -> TSAnalysis | None:
        return self._results.get(symbol)

    def get_trades(self, symbol: str) -> list[TradeEvent]:
        return list(self._trades.get(symbol, []))

    async def _on_trade(self, event: TradeEvent) -> None:
        # Store trade
        if event.ticker not in self._trades:
            self._trades[event.ticker] = deque(maxlen=_MAX_HISTORY)
        self._trades[event.ticker].append(event)

        # Recompute analysis
        result = self.analyze(event.ticker)
        self._results[event.ticker] = result

    def analyze(self, symbol: str) -> TSAnalysis:
        """Compute T&S analysis from stored trades for a symbol."""
        trades = list(self._trades.get(symbol, []))
        if not trades:
            return TSAnalysis(
                ticker=symbol,
                total_trades=0,
                bid_hits=0,
                ask_hits=0,
                unknown_trades=0,
                buy_sell_ratio=_ZERO,
                is_bullish=False,
            )

        bid_hits = sum(1 for t in trades if t.side == "bid")
        ask_hits = sum(1 for t in trades if t.side == "ask")
        unknown = sum(1 for t in trades if t.side == "unknown")

        if bid_hits > 0:
            ratio = Decimal(str(ask_hits)) / Decimal(str(bid_hits))
        else:
            ratio = Decimal("Infinity") if ask_hits > 0 else _ZERO

        # Block trade detection
        blocks = self._detect_blocks(trades)

        # Recent MM IDs
        mm_ids = tuple(dict.fromkeys(t.mm_id for t in trades[-20:] if t.mm_id))

        return TSAnalysis(
            ticker=symbol,
            total_trades=len(trades),
            bid_hits=bid_hits,
            ask_hits=ask_hits,
            unknown_trades=unknown,
            buy_sell_ratio=ratio,
            is_bullish=ratio > _ONE,
            block_trades=tuple(blocks),
            recent_mm_ids=mm_ids,
        )

    def _detect_blocks(self, trades: list[TradeEvent]) -> list[BlockTrade]:
        """Detect block trades — multiple fills at same price within time window."""
        if len(trades) < _BLOCK_MIN_TRADES:
            return []

        blocks: list[BlockTrade] = []
        i = 0
        while i < len(trades):
            group = [trades[i]]
            j = i + 1
            while j < len(trades):
                dt = abs((trades[j].timestamp - trades[i].timestamp).total_seconds())
                if dt <= _BLOCK_TIME_WINDOW_SEC and trades[j].price == trades[i].price:
                    group.append(trades[j])
                    j += 1
                else:
                    break

            if len(group) >= _BLOCK_MIN_TRADES:
                blocks.append(BlockTrade(
                    price=group[0].price,
                    total_size=sum(t.size for t in group),
                    fill_count=len(group),
                    side=group[0].side,
                    timestamp=group[0].timestamp,
                ))

            i = j if j > i + 1 else i + 1

        return blocks

    def reset_symbol(self, symbol: str) -> None:
        """Clear all trades and analysis for a symbol."""
        self._trades.pop(symbol, None)
        self._results.pop(symbol, None)
