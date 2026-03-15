"""IBKR broker adapter using ib_async.

Translates ib_async callbacks into internal events published on the EventBus.
Handles auto-reconnect with exponential backoff.
"""

import asyncio
from decimal import Decimal

import structlog
from ib_async import IB, Stock

from config.settings import IBKRSettings, get_settings
from src.broker.adapter import BrokerAdapter
from src.core.event_bus import EventBus
from src.core.events import L2UpdateEvent, MarketDataEvent, TradeEvent

logger = structlog.get_logger(__name__)

_VALID_EXCHANGES = {"PINK", "GREY"}
_MAX_BACKOFF = 60


class IBAdapter(BrokerAdapter):
    """Real IBKR implementation using ib_async."""

    def __init__(
        self,
        event_bus: EventBus,
        settings: IBKRSettings | None = None,
    ) -> None:
        super().__init__(event_bus)
        self._settings = settings or get_settings().ibkr
        self._ib = IB()
        self._contracts: dict[str, Stock] = {}
        self._subscriptions: dict[str, set[str]] = {}
        self._backoff = 1
        self._reconnecting = False
        self._background_tasks: set[asyncio.Task] = set()

    # ── Lifecycle ────────────────────────────────────────────────

    async def connect(self) -> None:
        await self._ib.connectAsync(
            host=self._settings.host,
            port=self._settings.port,
            clientId=self._settings.client_id_data,
            timeout=self._settings.timeout,
        )
        self._ib.pendingTickersEvent += self._on_pending_tickers
        self._ib.disconnectedEvent += self._on_disconnect
        self._ib.errorEvent += self._on_error
        self._backoff = 1
        logger.info(
            "ibkr_connected",
            host=self._settings.host,
            port=self._settings.port,
            client_id=self._settings.client_id_data,
        )

    async def disconnect(self) -> None:
        self._reconnecting = False
        self._ib.pendingTickersEvent -= self._on_pending_tickers
        self._ib.disconnectedEvent -= self._on_disconnect
        self._ib.errorEvent -= self._on_error
        self._ib.disconnect()
        self._contracts.clear()
        self._subscriptions.clear()
        logger.info("ibkr_disconnected")

    def is_connected(self) -> bool:
        return self._ib.isConnected()

    # ── Contract creation ────────────────────────────────────────

    async def create_otc_contract(
        self, symbol: str, exchange: str = "PINK"
    ) -> object:
        exchange = exchange.upper()
        if exchange not in _VALID_EXCHANGES:
            raise ValueError(f"Invalid OTC exchange: {exchange!r} (expected PINK or GREY)")

        if symbol in self._contracts:
            return self._contracts[symbol]

        contract = Stock(symbol, exchange, "USD")
        qualified = await self._ib.qualifyContractsAsync(contract)
        if not qualified:
            raise ValueError(f"Could not qualify contract for {symbol} on {exchange}")

        self._contracts[symbol] = qualified[0]
        logger.info("contract_qualified", symbol=symbol, exchange=exchange)
        return qualified[0]

    # ── Market data (L1) ─────────────────────────────────────────

    async def subscribe_market_data(self, symbol: str, exchange: str) -> None:
        self._ensure_connected()
        contract = await self.create_otc_contract(symbol, exchange)
        self._ib.reqMktData(contract)
        self._track_sub(symbol, "market_data")
        logger.info("subscribed_market_data", symbol=symbol)

    async def unsubscribe_market_data(self, symbol: str) -> None:
        contract = self._contracts.get(symbol)
        if contract:
            self._ib.cancelMktData(contract)
            self._untrack_sub(symbol, "market_data")
            logger.info("unsubscribed_market_data", symbol=symbol)

    # ── L2 depth ─────────────────────────────────────────────────

    async def subscribe_l2_depth(
        self, symbol: str, exchange: str, num_rows: int = 5
    ) -> None:
        self._ensure_connected()
        contract = await self.create_otc_contract(symbol, exchange)
        self._ib.reqMktDepth(contract, numRows=num_rows, isSmartDepth=False)
        self._track_sub(symbol, "l2_depth")
        logger.info("subscribed_l2_depth", symbol=symbol, num_rows=num_rows)

    async def unsubscribe_l2_depth(self, symbol: str) -> None:
        contract = self._contracts.get(symbol)
        if contract:
            self._ib.cancelMktDepth(contract, isSmartDepth=False)
            self._untrack_sub(symbol, "l2_depth")
            logger.info("unsubscribed_l2_depth", symbol=symbol)

    # ── Tick-by-tick (Time & Sales) ──────────────────────────────

    async def subscribe_tick_by_tick(
        self, symbol: str, exchange: str, tick_type: str = "AllLast"
    ) -> None:
        self._ensure_connected()
        contract = await self.create_otc_contract(symbol, exchange)
        self._ib.reqTickByTickData(contract, tick_type)
        self._track_sub(symbol, "tick_by_tick")
        logger.info("subscribed_tick_by_tick", symbol=symbol, tick_type=tick_type)

    async def unsubscribe_tick_by_tick(self, symbol: str) -> None:
        contract = self._contracts.get(symbol)
        if contract:
            self._ib.cancelTickByTickData(contract, "AllLast")
            self._untrack_sub(symbol, "tick_by_tick")
            logger.info("unsubscribed_tick_by_tick", symbol=symbol)

    # ── Historical data ──────────────────────────────────────────

    async def request_historical_bars(
        self,
        symbol: str,
        exchange: str = "PINK",
        duration: str = "30 D",
        bar_size: str = "1 day",
    ) -> list[dict]:
        self._ensure_connected()
        contract = await self.create_otc_contract(symbol, exchange)
        bars = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,
        )
        result = []
        for bar in bars or []:
            result.append({
                "open": Decimal(str(bar.open)),
                "high": Decimal(str(bar.high)),
                "low": Decimal(str(bar.low)),
                "close": Decimal(str(bar.close)),
                "volume": int(bar.volume),
            })
        logger.info("historical_bars_loaded", symbol=symbol, count=len(result))
        return result

    # ── ib_async callback (sync → async bridge) ─────────────────

    def _on_pending_tickers(self, tickers: list) -> None:
        """Synchronous callback from ib_async. Schedules async processing."""
        for ticker in tickers:
            task = asyncio.create_task(self._process_ticker(ticker))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def _process_ticker(self, ticker) -> None:
        symbol = ticker.contract.symbol
        subs = self._subscriptions.get(symbol, set())

        if "market_data" in subs:
            await self._process_market_data(ticker)
        if "l2_depth" in subs:
            await self._process_dom_ticks(ticker)
        if "tick_by_tick" in subs:
            await self._process_tick_by_tick(ticker)

    async def _process_market_data(self, ticker) -> None:
        event = MarketDataEvent(
            ticker=ticker.contract.symbol,
            price=Decimal(str(ticker.last)) if ticker.last == ticker.last else Decimal("0"),
            bid=Decimal(str(ticker.bid)) if ticker.bid == ticker.bid else Decimal("0"),
            ask=Decimal(str(ticker.ask)) if ticker.ask == ticker.ask else Decimal("0"),
            volume=int(ticker.volume) if ticker.volume == ticker.volume else 0,
        )
        await self._event_bus.publish(event)

    async def _process_dom_ticks(self, ticker) -> None:
        bid_levels = tuple(
            (Decimal(str(d.price)), d.size, getattr(d, "marketMaker", ""))
            for d in (ticker.domBids or [])
        )
        ask_levels = tuple(
            (Decimal(str(d.price)), d.size, getattr(d, "marketMaker", ""))
            for d in (ticker.domAsks or [])
        )
        if bid_levels or ask_levels:
            event = L2UpdateEvent(
                ticker=ticker.contract.symbol,
                bid_levels=bid_levels,
                ask_levels=ask_levels,
            )
            await self._event_bus.publish(event)

    async def _process_tick_by_tick(self, ticker) -> None:
        for tick in ticker.tickByTicks or []:
            side = "unknown"
            if hasattr(tick, "price") and hasattr(ticker, "bid") and hasattr(ticker, "ask"):
                if tick.price == ticker.bid:
                    side = "bid"
                elif tick.price == ticker.ask:
                    side = "ask"

            event = TradeEvent(
                ticker=ticker.contract.symbol,
                price=Decimal(str(tick.price)),
                size=int(tick.size),
                side=side,
            )
            await self._event_bus.publish(event)

    # ── Reconnection ─────────────────────────────────────────────

    def _on_disconnect(self) -> None:
        if self._reconnecting:
            return
        logger.warning("ibkr_disconnected_unexpectedly")
        task = asyncio.create_task(self._reconnect_loop())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _reconnect_loop(self) -> None:
        self._reconnecting = True
        while self._reconnecting and not self._ib.isConnected():
            logger.info("ibkr_reconnecting", backoff=self._backoff)
            try:
                await self._ib.connectAsync(
                    host=self._settings.host,
                    port=self._settings.port,
                    clientId=self._settings.client_id_data,
                    timeout=self._settings.timeout,
                )
                self._backoff = 1
                logger.info("ibkr_reconnected")
                await self._resubscribe_all()
                return
            except Exception:
                logger.warning("ibkr_reconnect_failed", backoff=self._backoff)
                await asyncio.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, _MAX_BACKOFF)
        self._reconnecting = False

    async def _resubscribe_all(self) -> None:
        for symbol, sub_types in list(self._subscriptions.items()):
            contract = self._contracts.get(symbol)
            if not contract:
                continue
            exchange = contract.exchange
            if "market_data" in sub_types:
                await self.subscribe_market_data(symbol, exchange)
            if "l2_depth" in sub_types:
                await self.subscribe_l2_depth(symbol, exchange)
            if "tick_by_tick" in sub_types:
                await self.subscribe_tick_by_tick(symbol, exchange)
        logger.info("ibkr_resubscribed_all", count=len(self._subscriptions))

    # ── Error handling ───────────────────────────────────────────

    def _on_error(self, req_id: int, error_code: int, error_string: str, contract) -> None:
        logger.error(
            "ibkr_error",
            req_id=req_id,
            error_code=error_code,
            error_string=error_string,
            contract=str(contract) if contract else None,
        )

    # ── Helpers ──────────────────────────────────────────────────

    def _ensure_connected(self) -> None:
        if not self._ib.isConnected():
            raise ConnectionError("Not connected to IBKR")

    def _track_sub(self, symbol: str, sub_type: str) -> None:
        if symbol not in self._subscriptions:
            self._subscriptions[symbol] = set()
        self._subscriptions[symbol].add(sub_type)

    def _untrack_sub(self, symbol: str, sub_type: str) -> None:
        if symbol in self._subscriptions:
            self._subscriptions[symbol].discard(sub_type)
            if not self._subscriptions[symbol]:
                del self._subscriptions[symbol]
