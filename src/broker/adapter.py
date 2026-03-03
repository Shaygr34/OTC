"""Abstract broker adapter interface.

All broker implementations (IBKR, mock, future) implement this ABC.
Callers depend only on BrokerAdapter — never on broker-specific types.
"""

from abc import ABC, abstractmethod

from src.core.event_bus import EventBus


class BrokerAdapter(ABC):
    """Interface every broker implementation must satisfy.

    Constructor receives an EventBus. Implementations publish
    MarketDataEvent, L2UpdateEvent, and TradeEvent through it.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    # ── Lifecycle ────────────────────────────────────────────────

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the broker."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Cleanly disconnect from the broker."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the broker connection is active."""

    # ── Contract creation ────────────────────────────────────────

    @abstractmethod
    async def create_otc_contract(
        self, symbol: str, exchange: str = "PINK"
    ) -> object:
        """Create and qualify a broker-specific OTC contract.

        Returns ``object`` to avoid leaking broker library types
        into the abstract layer.
        """

    # ── Market data (L1) ─────────────────────────────────────────

    @abstractmethod
    async def subscribe_market_data(self, symbol: str, exchange: str) -> None:
        """Subscribe to L1 market data. Publishes MarketDataEvent."""

    @abstractmethod
    async def unsubscribe_market_data(self, symbol: str) -> None:
        """Cancel L1 market data subscription."""

    # ── L2 depth ─────────────────────────────────────────────────

    @abstractmethod
    async def subscribe_l2_depth(
        self, symbol: str, exchange: str, num_rows: int = 5
    ) -> None:
        """Subscribe to L2 market depth. Publishes L2UpdateEvent."""

    @abstractmethod
    async def unsubscribe_l2_depth(self, symbol: str) -> None:
        """Cancel L2 depth subscription."""

    # ── Tick-by-tick (Time & Sales) ──────────────────────────────

    @abstractmethod
    async def subscribe_tick_by_tick(
        self, symbol: str, exchange: str, tick_type: str = "AllLast"
    ) -> None:
        """Subscribe to tick-by-tick data. Publishes TradeEvent."""

    @abstractmethod
    async def unsubscribe_tick_by_tick(self, symbol: str) -> None:
        """Cancel tick-by-tick subscription."""
