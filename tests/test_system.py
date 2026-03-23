"""Tests for the system runner (Phase 8).

Covers: module wiring, start/stop lifecycle, event flow end-to-end,
shutdown signaling, adapter connectivity.
"""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from config.constants import PriceTier

# Import after events to avoid circular
from scripts.run_system import SystemRunner
from src.broker.mock import MockAdapter
from src.core.event_bus import EventBus
from src.core.events import (
    AnalysisCompleteEvent,
)
from src.scanner.stability import DailyBar


@pytest.fixture
def mock_runner():
    """Create a SystemRunner with MockAdapter injected (no IBKR needed)."""
    runner = SystemRunner()
    # Replace IBAdapter with MockAdapter for testing
    mock_adapter = MockAdapter(runner.event_bus)
    runner.adapter = mock_adapter
    runner._adapter_name = "mock"
    return runner

# ── Construction Tests ───────────────────────────────────────────


class TestSystemConstruction:
    def test_all_modules_constructed(self):
        runner = SystemRunner()
        assert runner.event_bus is not None
        assert runner.adapter is not None
        assert runner.screener is not None
        assert runner.l2_analyzer is not None
        assert runner.volume_analyzer is not None
        assert runner.ts_analyzer is not None
        assert runner.dilution_sentinel is not None
        assert runner.rule_engine is not None
        assert runner.alert_dispatcher is not None
        assert runner.telegram is not None

    def test_not_running_initially(self):
        runner = SystemRunner()
        assert runner.is_running is False

    def test_adapter_is_ibkr(self):
        runner = SystemRunner()
        from src.broker.ibkr import IBAdapter
        assert isinstance(runner.adapter, IBAdapter)


# ── Lifecycle Tests ──────────────────────────────────────────────


class TestLifecycle:
    async def test_start_connects_adapter(self, mock_runner):
        runner = mock_runner
        await runner.start()
        assert runner.adapter.is_connected()
        assert runner.is_running is True
        await runner.stop()

    async def test_stop_disconnects_adapter(self, mock_runner):
        runner = mock_runner
        await runner.start()
        await runner.stop()
        assert runner.adapter.is_connected() is False
        assert runner.is_running is False

    async def test_stop_idempotent(self, mock_runner):
        runner = mock_runner
        await runner.start()
        await runner.stop()
        await runner.stop()  # should not raise
        assert runner.is_running is False

    async def test_request_shutdown(self):
        runner = SystemRunner()
        runner.request_shutdown()
        assert runner._shutdown_event.is_set()


# ── Event Flow Tests (End-to-End) ────────────────────────────────


class TestEventFlow:
    async def test_market_data_reaches_screener(self, mock_runner):
        """MarketDataEvent flows through to screener."""
        runner = mock_runner
        await runner.start()

        # Seed bars so screener can evaluate
        _seed_stable_bars(runner, "ABCD", PriceTier.TRIPS)

        await runner.adapter.push_market_data(
            ticker="ABCD",
            price=Decimal("0.0003"),
            bid=Decimal("0.0003"),
            ask=Decimal("0.0004"),
            volume=50000,
        )

        # Volume analyzer should have a result
        vol = runner.volume_analyzer.get_result("ABCD")
        assert vol is not None

        await runner.stop()

    async def test_l2_update_reaches_analyzer(self, mock_runner):
        """L2UpdateEvent flows through to L2Analyzer."""
        runner = mock_runner
        await runner.start()

        await runner.adapter.push_l2_update(
            ticker="ABCD",
            bid_levels=(
                (Decimal("0.0003"), 500000, "ETRF"),
                (Decimal("0.0002"), 300000, "NITE"),
            ),
            ask_levels=(
                (Decimal("0.0004"), 100000, "VIRT"),
            ),
        )

        l2 = runner.l2_analyzer.get_result("ABCD")
        assert l2 is not None
        assert l2.imbalance_label in ("STRONG", "FAVORABLE", "INSUFFICIENT")

        await runner.stop()

    async def test_trade_reaches_ts_analyzer(self, mock_runner):
        """TradeEvent flows through to TSAnalyzer."""
        runner = mock_runner
        await runner.start()

        await runner.adapter.push_trade(
            ticker="ABCD",
            price=Decimal("0.0003"),
            size=100000,
            side="ask",
        )

        ts = runner.ts_analyzer.get_result("ABCD")
        assert ts is not None
        assert ts.total_trades == 1

        await runner.stop()

    async def test_full_pipeline_scanner_to_analysis(self, mock_runner):
        """Full flow: seed data → market event → scanner hit → rule engine."""
        runner = mock_runner
        await runner.start()

        # Seed stable bars + volume history
        _seed_stable_bars(runner, "BEST", PriceTier.TRIPS)
        for _ in range(15):
            runner.volume_analyzer.add_volume("BEST", 50000)

        # Inject L2 showing strong imbalance
        await runner.adapter.push_l2_update(
            ticker="BEST",
            bid_levels=(
                (Decimal("0.0003"), 500000, "ETRF"),
                (Decimal("0.0002"), 300000, "NITE"),
            ),
            ask_levels=(
                (Decimal("0.0004"), 50000, "VIRT"),
            ),
        )

        # Inject bullish T&S
        for _ in range(5):
            await runner.adapter.push_trade(
                ticker="BEST",
                price=Decimal("0.0004"),
                size=50000,
                side="ask",
            )
        for _ in range(2):
            await runner.adapter.push_trade(
                ticker="BEST",
                price=Decimal("0.0003"),
                size=20000,
                side="bid",
            )

        # Track AnalysisCompleteEvent
        received: list[AnalysisCompleteEvent] = []
        runner.event_bus.subscribe(
            AnalysisCompleteEvent, AsyncMock(side_effect=received.append)
        )

        # Push market data → triggers screener → scanner hit → rule engine
        await runner.adapter.push_market_data(
            ticker="BEST",
            price=Decimal("0.0003"),
            bid=Decimal("0.0003"),
            ask=Decimal("0.0004"),
            volume=50000,
        )

        # Verify rule engine scored it
        score = runner.rule_engine.get_result("BEST")
        assert score is not None
        assert score.total_score > Decimal("0")

        await runner.stop()

    async def test_alerts_dispatched_on_volume_anomaly(self, mock_runner):
        """Volume anomaly → AlertEvent → dispatcher."""
        runner = mock_runner
        await runner.start()

        # Seed low volume history
        for _ in range(10):
            runner.volume_analyzer.add_volume("SPIK", 1000)

        # Push extreme volume
        await runner.adapter.push_market_data(
            ticker="SPIK",
            price=Decimal("0.005"),
            bid=Decimal("0.005"),
            ask=Decimal("0.006"),
            volume=100000,
        )

        # Dispatcher should have received the alert
        assert len(runner.alert_dispatcher.history) > 0
        alert = runner.alert_dispatcher.history[0]
        assert alert.ticker == "SPIK"
        assert alert.source == "alert"

        await runner.stop()


# ── Helpers ──────────────────────────────────────────────────────


def _seed_stable_bars(
    runner: SystemRunner, symbol: str, tier: PriceTier,
) -> None:
    """Seed 30 stable daily bars for a symbol into the screener."""
    if tier in (PriceTier.TRIP_ZERO, PriceTier.TRIPS):
        price = Decimal("0.0003")
    elif tier in (PriceTier.LOW_DUBS, PriceTier.DUBS):
        price = Decimal("0.005")
    else:
        price = Decimal("0.02")

    for _ in range(30):
        bar = DailyBar(
            open=price,
            high=price + Decimal("0.0001"),
            low=price - Decimal("0.0001"),
            close=price,
            volume=50000,
        )
        runner.screener.add_daily_bar(symbol, bar)
