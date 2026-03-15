"""Main entry point — wires all modules and runs the ATM Trading Engine.

EventBus → MockAdapter (or IBAdapter) → Screener → all analyzers →
RuleEngine → AlertDispatcher. Async main loop.
"""

import asyncio
import os
import signal

import structlog

from config.settings import Settings, get_settings
from src.alerts.dispatcher import AlertDispatcher
from src.alerts.telegram import TelegramChannel
from src.database.persistence import DatabasePersistence
from src.database.repository import Repository, get_engine, get_session_factory
from src.database.schema import create_all_tables
from src.analysis.dilution import DilutionSentinel
from src.analysis.level2 import L2Analyzer
from src.analysis.time_sales import TSAnalyzer
from src.analysis.volume import VolumeAnalyzer
from src.broker.history import HistoryLoader
from src.broker.mock import MockAdapter
from src.core.event_bus import EventBus
from src.database.persistence import PersistenceSubscriber
from src.database.repository import Repository, get_engine, get_session_factory
from src.database.schema import create_all_tables
from src.rules.engine import RuleEngine, load_rules
from src.scanner.screener import Screener
from src.scanner.watchlist import load_watchlist

logger = structlog.get_logger(__name__)


class SystemRunner:
    """Composition root: constructs, wires, and runs the full v0 pipeline.

    All modules are constructed in dependency order. EventBus subscriptions
    are registered via each module's ``start()`` method.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._running = False
        self._shutdown_event = asyncio.Event()

        # ── Core ──
        self.event_bus = EventBus()

        # ── Adapter selection ──
        # Use IBAdapter only when explicitly enabled via ATM_USE_IBKR=1
        use_ibkr = os.environ.get("ATM_USE_IBKR", "").lower() in ("1", "true", "yes")
        if use_ibkr:
            from src.broker.ibkr import IBAdapter

            self.adapter = IBAdapter(self.event_bus, self._settings.ibkr)
            self._adapter_name = "ibkr"
        else:
            self.adapter = MockAdapter(self.event_bus)
            self._adapter_name = "mock"

        # ── Database ──
        self._engine = get_engine(self._settings.database.url)
        self._session_factory = get_session_factory(self._engine)
        self._repo = Repository(self._session_factory)
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

        # ── Database ──
        db_url = self._settings.database.url
        self._engine = get_engine(db_url)
        self._session_factory = get_session_factory(self._engine)
        self.repository = Repository(self._session_factory)
        self.db_persistence = DatabasePersistence(self.event_bus, self.repository)

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

        # Initialize database
        await create_all_tables(self._engine)

        # Create database tables (idempotent)
        await create_all_tables(self._engine)

        # Connect broker adapter
        await self.adapter.connect()

        # Load watchlist
        self._watchlist = load_watchlist()
        logger.info("watchlist_loaded", symbols=len(self._watchlist))

        # Seed historical data for stability metrics
        if self._watchlist:
            loaded = await HistoryLoader.seed(self._watchlist, self.adapter, self.screener)
            logger.info("history_complete", loaded=loaded)

        # Initialize Telegram if enabled
        if self._settings.telegram.enabled:
            await self.telegram.initialize()

        # Register all EventBus subscriptions (order matters)
        self.screener.start()
        self.l2_analyzer.start()
        self.volume_analyzer.start()
        self.ts_analyzer.start()
        self.rule_engine.start()
        self.db_persistence.start()
        self.alert_dispatcher.start()
        self.persistence.start()

        # Subscribe to live market data for all watchlist symbols
        for entry in self._watchlist:
            await self.adapter.subscribe_market_data(entry.ticker, entry.exchange)
            await self.adapter.subscribe_l2_depth(entry.ticker, entry.exchange)
            await self.adapter.subscribe_tick_by_tick(entry.ticker, entry.exchange)
        logger.info("subscriptions_active", symbols=len(self._watchlist))

        self._running = True
        logger.info("system_started", modules=7, adapter=self._adapter_name)

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

        await self.adapter.disconnect()
        await self._engine.dispose()
        await self.telegram.shutdown()
        await self._engine.dispose()

        self.event_bus.reset()
        logger.info("system_stopped")

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
    runner = SystemRunner()
    _setup_signal_handlers(runner)
    await runner.run()


def main() -> None:
    """Synchronous entry point."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
