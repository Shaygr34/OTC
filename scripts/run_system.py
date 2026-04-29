"""Main entry point — wires all modules and runs the ATM Trading Engine.

EventBus → MockAdapter (or IBAdapter) → Screener → all analyzers →
RuleEngine → AlertDispatcher. Async main loop.
"""

import asyncio
import contextlib
import json
import os
import signal
from pathlib import Path

import structlog

from config.logging import setup_logging
from config.settings import Settings, get_settings
from src.alerts.dispatcher import AlertDispatcher
from src.alerts.telegram import TelegramChannel
from src.analysis.dilution import DilutionSentinel
from src.analysis.level2 import L2Analyzer
from src.analysis.time_sales import TSAnalyzer
from src.analysis.volume import VolumeAnalyzer
from src.broker.history import HistoryLoader
from src.broker.ibkr import IBAdapter
from src.core.event_bus import EventBus
from src.core.ticker_watcher import TickerWatcher
from src.database.persistence import PersistenceSubscriber
from src.database.repository import Repository, get_engine, get_session_factory
from src.database.schema import create_all_tables
from src.rules.engine import RuleEngine, load_rules
from src.scanner.screener import Screener
from src.scanner.universe import UniverseScanner
from src.scanner.watchlist import WatchlistEntry, load_watchlist

logger = structlog.get_logger(__name__)


class SystemRunner:
    """Composition root: constructs, wires, and runs the full v0 pipeline.

    All modules are constructed in dependency order. EventBus subscriptions
    are registered via each module's ``start()`` method.
    """

    def __init__(self, settings: Settings | None = None, adapter=None) -> None:
        self._settings = settings or get_settings()
        self._running = False
        self._shutdown_event = asyncio.Event()

        # ── Core ──
        self.event_bus = EventBus()

        # ── Adapter — injectable for tests, defaults to IBKR ──
        if adapter is not None:
            self.adapter = adapter
            self._adapter_name = "injected"
        else:
            self.adapter = IBAdapter(self.event_bus, self._settings.ibkr)
            self._adapter_name = "ibkr"

        # ── Database ──
        database_url = os.environ.get("DATABASE_URL", self._settings.database.url)
        use_postgres = "postgresql" in database_url
        self._engine = get_engine(database_url)
        self._session_factory = get_session_factory(self._engine)
        self._repo = Repository(self._session_factory, use_postgres=use_postgres)
        self.persistence = PersistenceSubscriber(self._repo, self.event_bus)

        # ── Scanner ──
        self.screener = Screener(self.event_bus)

        # ── Analyzers ──
        self.l2_analyzer = L2Analyzer(self.event_bus)
        self.volume_analyzer = VolumeAnalyzer(self.event_bus)
        self.ts_analyzer = TSAnalyzer(self.event_bus)
        self.dilution_sentinel = DilutionSentinel(
            self.event_bus,
            self.l2_analyzer,
            self.volume_analyzer,
            self.ts_analyzer,
        )

        # ── Rule Engine ──
        self.rule_engine = RuleEngine(
            event_bus=self.event_bus,
            screener=self.screener,
            l2_analyzer=self.l2_analyzer,
            volume_analyzer=self.volume_analyzer,
            ts_analyzer=self.ts_analyzer,
            dilution_sentinel=self.dilution_sentinel,
            rules=load_rules(),
        )

        # ── Ticker Watcher (DB → subscription bridge) ──
        self.ticker_watcher = TickerWatcher(
            repo=self._repo,
            adapter=self.adapter,
            screener=self.screener,
        )

        # ── Universe Scanner ──
        self.universe_scanner: UniverseScanner | None = None
        if self._settings.scanner.enabled:
            self.universe_scanner = UniverseScanner(
                adapter=self.adapter,
                repo=self._repo,
                settings=self._settings.scanner,
            )

        # ── Alerts ──
        telegram_settings = self._settings.telegram
        self.telegram = TelegramChannel(
            bot_token=telegram_settings.bot_token,
            chat_id=telegram_settings.chat_id,
        )
        self.alert_dispatcher = AlertDispatcher(
            event_bus=self.event_bus,
            telegram=self.telegram if telegram_settings.enabled else None,
        )

    async def start(self) -> None:
        """Connect adapter and start all modules."""
        logger.info("system_starting", adapter=self._adapter_name)

        # Initialize database (idempotent)
        await create_all_tables(self._engine)

        # Connect broker adapter
        await self.adapter.connect()

        # One-time import: migrate watchlist.yaml entries into candidates DB
        await self._import_watchlist_yaml()

        # Initialize Telegram if enabled
        if self._settings.telegram.enabled:
            await self.telegram.initialize()

        # Register all EventBus subscriptions (order matters)
        self.screener.start()
        self.l2_analyzer.start()
        self.volume_analyzer.start()
        self.ts_analyzer.start()
        self.rule_engine.start()
        self.persistence.start()
        self.alert_dispatcher.start()

        # Load active candidates from DB and subscribe
        active_candidates = await self._repo.get_candidates_by_statuses(
            ["active"]
        )
        for c in active_candidates:
            ex = getattr(c, "exchange", "PINK") or "PINK"
            try:
                await self.adapter.subscribe_market_data(c.ticker, ex)
                await self.adapter.subscribe_l2_depth(c.ticker, ex)
                await self.adapter.subscribe_tick_by_tick(c.ticker, ex)
            except Exception:
                logger.warning("subscribe_failed", ticker=c.ticker)
        logger.info("db_candidates_loaded", active=len(active_candidates))

        # Seed historical bars for active candidates
        if active_candidates:
            entries = [
                WatchlistEntry(
                    ticker=c.ticker,
                    exchange=getattr(c, "exchange", "PINK") or "PINK",
                )
                for c in active_candidates
            ]
            if entries:
                loaded = await HistoryLoader.seed(entries, self.adapter, self.screener)
                logger.info("history_complete", loaded=loaded)

        # Process any manual candidates, then start polling for new ones
        await self.ticker_watcher.activate_existing()
        self.ticker_watcher.start()
        logger.info("ticker_watcher_started")

        # Start universe scanner if enabled
        if self.universe_scanner is not None:
            await self.universe_scanner.start()

        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("system_started", modules=7, adapter=self._adapter_name)

    async def _heartbeat_loop(self) -> None:
        """Write engine status file every 10s so the dashboard can detect us."""
        status_path = Path(__file__).resolve().parent.parent / "data" / "engine_status.json"
        while self._running:
            try:
                status = {
                    "running": True,
                    "adapter": self._adapter_name,
                    "ibkr_connected": self._adapter_name == "ibkr"
                    and getattr(self.adapter, "is_connected", lambda: False)(),
                    "ibkr_host": self._settings.ibkr.host,
                    "ibkr_port": self._settings.ibkr.port,
                }
                status_path.write_text(json.dumps(status))
            except Exception:
                pass
            await asyncio.sleep(10)
        # Clean up on stop
        with contextlib.suppress(OSError):
            status_path.unlink()

    async def run(self) -> None:
        """Run the main loop until shutdown is signaled."""
        await self.start()

        logger.info("system_running", msg="Waiting for events. Ctrl+C to stop.")

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        await self.stop()

    async def stop(self) -> None:
        """Gracefully shut down all modules."""
        if not self._running:
            return

        logger.info("system_stopping")
        self._running = False

        # Cancel heartbeat
        if hasattr(self, "_heartbeat_task") and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task

        # Remove status file
        status_path = Path(__file__).resolve().parent.parent / "data" / "engine_status.json"
        with contextlib.suppress(OSError):
            status_path.unlink()

        if self.universe_scanner is not None:
            await self.universe_scanner.stop()
        await self.ticker_watcher.stop()
        await self.adapter.disconnect()
        await self._engine.dispose()
        await self.telegram.shutdown()

        self.event_bus.reset()
        logger.info("system_stopped")

    async def _import_watchlist_yaml(self) -> None:
        """One-time import: migrate watchlist.yaml entries into candidates DB.

        If watchlist.yaml has entries, insert them as active candidates
        (skipping duplicates). This lets existing users transition from
        YAML-based config to DB-based management without losing their list.
        """
        watchlist = load_watchlist()
        if not watchlist:
            return

        imported = 0
        for entry in watchlist:
            try:
                await self._repo.upsert_candidate(
                    ticker=entry.ticker,
                    price_tier="UNKNOWN",
                    status="active",
                    exchange=entry.exchange,
                )
                imported += 1
            except Exception:
                logger.warning("watchlist_import_failed", ticker=entry.ticker)
        if imported:
            logger.info("watchlist_yaml_imported", count=imported)

    def request_shutdown(self) -> None:
        """Signal the main loop to exit."""
        self._shutdown_event.set()

    @property
    def is_running(self) -> bool:
        return self._running


def _setup_signal_handlers(runner: SystemRunner) -> None:
    """Register SIGINT/SIGTERM handlers for graceful shutdown."""
    import sys

    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, runner.request_shutdown)
    else:
        # Windows: use signal.signal for SIGINT (Ctrl+C)
        def _handler(signum: int, frame: object) -> None:
            runner.request_shutdown()

        signal.signal(signal.SIGINT, _handler)


async def async_main() -> None:
    """Async entry point."""
    settings = get_settings()
    setup_logging(level=settings.log.level)
    runner = SystemRunner(settings)
    _setup_signal_handlers(runner)
    await runner.run()


def main() -> None:
    """Synchronous entry point."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
