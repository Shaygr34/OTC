"""TickerWatcher — polls the DB for manual candidates and activates them.

Bridges the gap between the dashboard (writes to DB) and the engine
(subscribes to IBKR). Runs as an asyncio task inside SystemRunner.
"""

import asyncio
import contextlib
from decimal import Decimal

import structlog

from config.constants import get_tier
from src.broker.adapter import BrokerAdapter
from src.broker.history import HistoryLoader
from src.database.repository import Repository
from src.scanner.screener import Screener
from src.scanner.watchlist import WatchlistEntry

logger = structlog.get_logger(__name__)

POLL_INTERVAL_SECONDS = 5

# Exchanges to try when qualifying a contract, in order.
_EXCHANGE_FALLBACKS = ("PINK", "GREY")


class TickerWatcher:
    """Polls the candidates table for status='manual' rows and subscribes."""

    def __init__(
        self,
        repo: Repository,
        adapter: BrokerAdapter,
        screener: Screener,
        poll_interval: float = POLL_INTERVAL_SECONDS,
    ) -> None:
        self._repo = repo
        self._adapter = adapter
        self._screener = screener
        self._poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._activated: set[str] = set()

    def start(self) -> None:
        """Launch the polling loop as a background task."""
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Cancel the polling task and wait for it to finish."""
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _poll_loop(self) -> None:
        """Check for manual candidates every POLL_INTERVAL_SECONDS."""
        while True:
            try:
                await self._process_manual_tickers()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("ticker_watcher_poll_error")
            await asyncio.sleep(self._poll_interval)

    async def _process_manual_tickers(self) -> None:
        """Find and activate all status='manual' candidates."""
        candidates = await self._repo.get_candidates_by_status("manual")
        for candidate in candidates:
            ticker = candidate.ticker
            if ticker in self._activated:
                continue
            await self._activate_ticker(
                ticker, getattr(candidate, "exchange", "PINK") or "PINK"
            )

    async def _activate_ticker(self, ticker: str, exchange: str) -> None:
        """Qualify contract, subscribe, seed history, update DB."""
        logger.info("ticker_activating", ticker=ticker, exchange=exchange)

        # Try the specified exchange first, then fallbacks
        exchanges_to_try = [exchange]
        for fb in _EXCHANGE_FALLBACKS:
            if fb not in exchanges_to_try:
                exchanges_to_try.append(fb)

        qualified_exchange = None
        for ex in exchanges_to_try:
            try:
                await self._adapter.create_otc_contract(ticker, ex)
                qualified_exchange = ex
                break
            except (ValueError, ConnectionError):
                logger.debug(
                    "contract_qualify_failed",
                    ticker=ticker,
                    exchange=ex,
                )
                continue

        if qualified_exchange is None:
            logger.warning("ticker_rejected", ticker=ticker, reason="contract_not_found")
            await self._repo.reject_candidate(ticker, "IBKR contract not found")
            self._activated.add(ticker)
            return

        # Subscribe to all data feeds
        await self._adapter.subscribe_market_data(ticker, qualified_exchange)
        await self._adapter.subscribe_l2_depth(ticker, qualified_exchange)
        await self._adapter.subscribe_tick_by_tick(ticker, qualified_exchange)

        # Seed historical bars
        entry = WatchlistEntry(ticker=ticker, exchange=qualified_exchange)
        await HistoryLoader.seed([entry], self._adapter, self._screener)

        # Determine price tier from historical data (use last close if available)
        price_tier = "UNKNOWN"
        try:
            bars = await self._adapter.request_historical_bars(
                ticker, qualified_exchange
            )
            if bars:
                last_close = Decimal(str(bars[-1]["close"]))
                tier = get_tier(last_close)
                if tier is not None:
                    price_tier = tier.value
        except Exception:
            logger.debug("tier_detection_failed", ticker=ticker)

        # Update DB: manual → active
        await self._repo.activate_candidate(ticker, price_tier, qualified_exchange)
        self._activated.add(ticker)

        logger.info(
            "ticker_activated",
            ticker=ticker,
            exchange=qualified_exchange,
            price_tier=price_tier,
        )

    async def activate_existing(self) -> None:
        """On startup, process any leftover manual candidates."""
        await self._process_manual_tickers()
