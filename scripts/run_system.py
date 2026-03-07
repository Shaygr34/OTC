"""Main entry point — wires all modules and runs the ATM Trading Engine.

EventBus → MockAdapter (or IBAdapter) → Screener → all analyzers →
RuleEngine → AlertDispatcher. Async main loop.
"""

import asyncio
import signal

import structlog

from config.settings import Settings, get_settings
from src.alerts.dispatcher import AlertDispatcher
from src.alerts.telegram import TelegramChannel
from src.analysis.dilution import DilutionSentinel
from src.analysis.level2 import L2Analyzer
from src.analysis.time_sales import TSAnalyzer
from src.analysis.volume import VolumeAnalyzer
from src.broker.mock import MockAdapter
from src.core.event_bus import EventBus
from src.rules.engine import RuleEngine, load_rules
from src.scanner.screener import Screener

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
        self.adapter = MockAdapter(self.event_bus)

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
        logger.info("system_starting")

        # Connect broker adapter
        await self.adapter.connect()

        # Initialize Telegram if enabled
        if self._settings.telegram.enabled:
            await self.telegram.initialize()

        # Register all EventBus subscriptions (order matters)
        self.screener.start()
        self.l2_analyzer.start()
        self.volume_analyzer.start()
        self.ts_analyzer.start()
        self.rule_engine.start()
        self.alert_dispatcher.start()

        self._running = True
        logger.info("system_started", modules=6)

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
        await self.telegram.shutdown()

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
