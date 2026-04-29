"""Mock broker adapter for testing without a running TWS instance.

Implements the same BrokerAdapter interface as IBAdapter, plus ``push_*``
methods to inject synthetic events for Phases 3-6 development.
"""

from dataclasses import dataclass
from decimal import Decimal

import structlog

from src.broker.adapter import BrokerAdapter
from src.core.event_bus import EventBus
from src.core.events import L2UpdateEvent, MarketDataEvent, TradeEvent

logger = structlog.get_logger(__name__)

_VALID_EXCHANGES = {"SMART", "PINK", "GREY", "OTC", "VALUE", "PINKC"}


@dataclass(frozen=True)
class MockContract:
    """Lightweight stand-in for ib_async.Stock."""

    symbol: str
    exchange: str = "PINK"
    currency: str = "USD"
    con_id: int = 0


class MockAdapter(BrokerAdapter):
    """Fake broker adapter for development and testing."""

    def __init__(self, event_bus: EventBus) -> None:
        super().__init__(event_bus)
        self._connected = False
        self._contracts: dict[str, MockContract] = {}
        self._subscriptions: dict[str, set[str]] = {}
        self._historical_data: dict[str, list[dict]] = {}
        self._scanner_results: list = []
        self._next_con_id = 1

    # ── Lifecycle ────────────────────────────────────────────────

    async def connect(self) -> None:
        self._connected = True
        logger.info("mock_connected")

    async def disconnect(self) -> None:
        self._connected = False
        self._contracts.clear()
        self._subscriptions.clear()
        logger.info("mock_disconnected")

    def is_connected(self) -> bool:
        return self._connected

    # ── Contract creation ────────────────────────────────────────

    async def create_otc_contract(
        self, symbol: str, exchange: str = "PINK"
    ) -> object:
        self._ensure_connected()
        exchange = exchange.upper()
        if exchange not in _VALID_EXCHANGES:
            raise ValueError(
                f"Invalid OTC exchange: {exchange!r} "
                f"(expected one of {', '.join(sorted(_VALID_EXCHANGES))})"
            )

        if symbol in self._contracts:
            return self._contracts[symbol]

        contract = MockContract(
            symbol=symbol,
            exchange=exchange,
            con_id=self._next_con_id,
        )
        self._next_con_id += 1
        self._contracts[symbol] = contract
        return contract

    # ── Market data (L1) ─────────────────────────────────────────

    async def subscribe_market_data(self, symbol: str, exchange: str) -> None:
        self._ensure_connected()
        await self.create_otc_contract(symbol, exchange)
        self._track_sub(symbol, "market_data")

    async def unsubscribe_market_data(self, symbol: str) -> None:
        self._untrack_sub(symbol, "market_data")

    # ── L2 depth ─────────────────────────────────────────────────

    async def subscribe_l2_depth(
        self, symbol: str, exchange: str, num_rows: int = 5
    ) -> None:
        self._ensure_connected()
        await self.create_otc_contract(symbol, exchange)
        self._track_sub(symbol, "l2_depth")

    async def unsubscribe_l2_depth(self, symbol: str) -> None:
        self._untrack_sub(symbol, "l2_depth")

    # ── Tick-by-tick (Time & Sales) ──────────────────────────────

    async def subscribe_tick_by_tick(
        self, symbol: str, exchange: str, tick_type: str = "AllLast"
    ) -> None:
        self._ensure_connected()
        await self.create_otc_contract(symbol, exchange)
        self._track_sub(symbol, "tick_by_tick")

    async def unsubscribe_tick_by_tick(self, symbol: str) -> None:
        self._untrack_sub(symbol, "tick_by_tick")

    # ── Synthetic data injection (test helpers) ──────────────────

    async def push_market_data(
        self,
        ticker: str,
        price: Decimal,
        bid: Decimal,
        ask: Decimal,
        volume: int,
    ) -> None:
        """Inject a synthetic MarketDataEvent. Awaits all handlers."""
        self._ensure_connected()
        event = MarketDataEvent(
            ticker=ticker,
            price=price,
            bid=bid,
            ask=ask,
            volume=volume,
        )
        await self._event_bus.publish(event)

    async def push_l2_update(
        self,
        ticker: str,
        bid_levels: tuple[tuple[Decimal, int, str], ...],
        ask_levels: tuple[tuple[Decimal, int, str], ...],
    ) -> None:
        """Inject a synthetic L2UpdateEvent. Awaits all handlers."""
        self._ensure_connected()
        event = L2UpdateEvent(
            ticker=ticker,
            bid_levels=bid_levels,
            ask_levels=ask_levels,
        )
        await self._event_bus.publish(event)

    async def push_trade(
        self,
        ticker: str,
        price: Decimal,
        size: int,
        side: str = "unknown",
        mm_id: str = "",
    ) -> None:
        """Inject a synthetic TradeEvent. Awaits all handlers."""
        self._ensure_connected()
        event = TradeEvent(
            ticker=ticker,
            price=price,
            size=size,
            side=side,
            mm_id=mm_id,
        )
        await self._event_bus.publish(event)

    # ── Historical data ──────────────────────────────────────────

    async def request_historical_bars(
        self,
        symbol: str,
        exchange: str = "PINK",
        duration: str = "30 D",
        bar_size: str = "1 day",
    ) -> list[dict]:
        """Return injectable test data, or empty list by default."""
        self._ensure_connected()
        return list(self._historical_data.get(symbol, []))

    def set_historical_data(self, symbol: str, bars: list[dict]) -> None:
        """Inject historical bar data for testing."""
        self._historical_data[symbol] = bars

    # ── Scanner ──────────────────────────────────────────────

    async def request_scanner(self, subscription: object) -> list:
        self._ensure_connected()
        return list(self._scanner_results)

    async def get_scanner_parameters(self) -> str:
        self._ensure_connected()
        return "<xml>mock scanner parameters</xml>"

    def set_scanner_results(self, results: list) -> None:
        """Inject scanner results for testing."""
        self._scanner_results = results

    # ── Introspection (for test assertions) ──────────────────────

    def get_subscriptions(self, symbol: str) -> set[str]:
        """Return the set of active subscription types for a symbol."""
        return self._subscriptions.get(symbol, set()).copy()

    # ── Helpers ──────────────────────────────────────────────────

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise ConnectionError("MockAdapter is not connected")

    def _track_sub(self, symbol: str, sub_type: str) -> None:
        if symbol not in self._subscriptions:
            self._subscriptions[symbol] = set()
        self._subscriptions[symbol].add(sub_type)

    def _untrack_sub(self, symbol: str, sub_type: str) -> None:
        if symbol in self._subscriptions:
            self._subscriptions[symbol].discard(sub_type)
            if not self._subscriptions[symbol]:
                del self._subscriptions[symbol]
