"""Tests for src/analysis/ — L2, volume, time & sales, and dilution modules.

Covers threshold logic, event flow, Decimal precision, edge cases,
and cross-module integration via the dilution sentinel.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from src.analysis.dilution import DilutionSentinel
from src.analysis.level2 import L2Analyzer
from src.analysis.time_sales import TSAnalyzer
from src.analysis.volume import VolumeAnalyzer
from src.core.event_bus import EventBus
from src.core.events import (
    AlertEvent,
    DilutionAlertEvent,
    L2UpdateEvent,
    MarketDataEvent,
    TradeEvent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collector(target: list):
    async def _handler(event):
        target.append(event)
    return _handler


def _l2_event(
    ticker: str = "ABCD",
    bids: tuple[tuple[str, int, str], ...] = (),
    asks: tuple[tuple[str, int, str], ...] = (),
) -> L2UpdateEvent:
    """Build an L2UpdateEvent from simplified bid/ask tuples (price_str, size, mm_id)."""
    return L2UpdateEvent(
        ticker=ticker,
        bid_levels=tuple((Decimal(p), s, mm) for p, s, mm in bids),
        ask_levels=tuple((Decimal(p), s, mm) for p, s, mm in asks),
    )


def _trade_event(
    ticker: str = "ABCD",
    price: str = "0.0002",
    size: int = 100_000,
    side: str = "ask",
    mm_id: str = "",
    ts: datetime | None = None,
) -> TradeEvent:
    return TradeEvent(
        ticker=ticker,
        price=Decimal(price),
        size=size,
        side=side,
        mm_id=mm_id,
        timestamp=ts or datetime.now(UTC),
    )


@pytest.fixture
def bus():
    b = EventBus()
    yield b
    b.reset()


# ===========================================================================
# L2 Analyzer
# ===========================================================================


class TestL2Imbalance:
    async def test_strong_imbalance(self, bus):
        analyzer = L2Analyzer(bus)
        event = _l2_event(
            bids=(("0.0002", 5_000_000, "NITE"),),
            asks=(("0.0003", 500_000, "CSTI"),),
        )
        result = analyzer.analyze(event)
        assert result.imbalance_ratio == Decimal("10")
        assert result.imbalance_label == "STRONG"

    async def test_favorable_imbalance(self, bus):
        analyzer = L2Analyzer(bus)
        event = _l2_event(
            bids=(("0.0002", 3_000_000, "NITE"),),
            asks=(("0.0003", 800_000, "CSTI"),),
        )
        result = analyzer.analyze(event)
        assert result.imbalance_ratio >= Decimal("3.0")
        assert result.imbalance_label == "FAVORABLE"

    async def test_insufficient_imbalance(self, bus):
        analyzer = L2Analyzer(bus)
        event = _l2_event(
            bids=(("0.0002", 1_000_000, "NITE"),),
            asks=(("0.0003", 1_000_000, "MAXM"),),
        )
        result = analyzer.analyze(event)
        assert result.imbalance_ratio == Decimal("1")
        assert result.imbalance_label == "INSUFFICIENT"

    async def test_zero_ask_shares(self, bus):
        analyzer = L2Analyzer(bus)
        event = _l2_event(bids=(("0.0002", 1_000_000, "NITE"),))
        result = analyzer.analyze(event)
        assert result.imbalance_ratio == Decimal("Infinity")

    async def test_both_empty(self, bus):
        analyzer = L2Analyzer(bus)
        event = _l2_event()
        result = analyzer.analyze(event)
        assert result.imbalance_ratio == Decimal("0")
        assert result.total_bid_shares == 0
        assert result.total_ask_shares == 0


class TestL2BadMM:
    async def test_bad_mm_on_ask_detected(self, bus):
        analyzer = L2Analyzer(bus)
        event = _l2_event(
            bids=(("0.0002", 1_000_000, "NITE"),),
            asks=(("0.0003", 500_000, "MAXM"),),
        )
        result = analyzer.analyze(event)
        assert result.has_bad_mm_on_ask is True
        assert "MAXM" in result.bad_mm_list

    async def test_no_bad_mm(self, bus):
        analyzer = L2Analyzer(bus)
        event = _l2_event(
            bids=(("0.0002", 1_000_000, "NITE"),),
            asks=(("0.0003", 500_000, "CSTI"),),
        )
        result = analyzer.analyze(event)
        assert result.has_bad_mm_on_ask is False
        assert result.bad_mm_list == []

    async def test_bad_mm_on_bid_not_flagged(self, bus):
        """Bad MMs on the bid side do NOT trigger has_bad_mm_on_ask."""
        analyzer = L2Analyzer(bus)
        event = _l2_event(
            bids=(("0.0002", 1_000_000, "MAXM"),),
            asks=(("0.0003", 500_000, "NITE"),),
        )
        result = analyzer.analyze(event)
        assert result.has_bad_mm_on_ask is False

    async def test_multiple_bad_mms(self, bus):
        analyzer = L2Analyzer(bus)
        event = _l2_event(
            bids=(("0.0002", 1_000_000, "NITE"),),
            asks=(
                ("0.0003", 300_000, "MAXM"),
                ("0.0004", 200_000, "GLED"),
            ),
        )
        result = analyzer.analyze(event)
        assert result.has_bad_mm_on_ask is True
        assert len(result.bad_mm_list) == 2


class TestL2WallDetection:
    async def test_wall_detected(self, bus):
        analyzer = L2Analyzer(bus)
        analyzer.set_adv("ABCD", 1_000_000)
        event = _l2_event(
            bids=(("0.0002", 100_000, "NITE"),),  # 10% of ADV → major wall
        )
        result = analyzer.analyze(event)
        assert len(result.bid_walls) == 1
        assert result.bid_walls[0].wall_ratio == Decimal("0.1")

    async def test_no_wall_below_threshold(self, bus):
        analyzer = L2Analyzer(bus)
        analyzer.set_adv("ABCD", 10_000_000)
        event = _l2_event(
            bids=(("0.0002", 10_000, "NITE"),),  # 0.1% of ADV → not a wall
        )
        result = analyzer.analyze(event)
        assert len(result.bid_walls) == 0

    async def test_wall_score_capped_at_10(self, bus):
        analyzer = L2Analyzer(bus)
        analyzer.set_adv("ABCD", 100_000)
        event = _l2_event(
            bids=(("0.0002", 500_000, "NITE"),),  # 500% of ADV
        )
        result = analyzer.analyze(event)
        assert result.bid_walls[0].wall_score == Decimal("10")

    async def test_no_adv_no_walls(self, bus):
        """Without ADV set, wall detection is skipped."""
        analyzer = L2Analyzer(bus)
        event = _l2_event(
            bids=(("0.0002", 5_000_000, "NITE"),),
        )
        result = analyzer.analyze(event)
        assert len(result.bid_walls) == 0


class TestL2EventSubscription:
    async def test_subscribes_and_stores(self, bus):
        analyzer = L2Analyzer(bus)
        analyzer.start()

        event = _l2_event(
            bids=(("0.0002", 1_000_000, "NITE"),),
            asks=(("0.0003", 500_000, "CSTI"),),
        )
        await bus.publish(event)

        result = analyzer.get_result("ABCD")
        assert result is not None
        assert result.imbalance_label == "INSUFFICIENT"


# ===========================================================================
# Volume Analyzer
# ===========================================================================


class TestVolumeZScore:
    async def test_normal_volume(self, bus):
        analyzer = VolumeAnalyzer(bus)
        for _ in range(20):
            analyzer.add_volume("ABCD", 100_000)

        result = analyzer.analyze("ABCD", 100_000)
        assert result.anomaly_level == "NORMAL"
        assert result.zscore == Decimal("0")

    async def test_notable_volume(self, bus):
        analyzer = VolumeAnalyzer(bus)
        for _ in range(20):
            analyzer.add_volume("ABCD", 100_000)

        # Inject some variance so std isn't zero
        analyzer.add_volume("ABCD", 120_000)
        result = analyzer.analyze("ABCD", 200_000)
        # With low std, this should be at least notable
        assert result.zscore > Decimal("0")

    async def test_extreme_volume(self, bus):
        analyzer = VolumeAnalyzer(bus)
        # Create history with moderate variance
        for i in range(20):
            analyzer.add_volume("ABCD", 100_000 + (i * 1000))

        result = analyzer.analyze("ABCD", 10_000_000)
        assert result.anomaly_level == "EXTREME"


class TestVolumeRVOL:
    async def test_rvol_calculation(self, bus):
        analyzer = VolumeAnalyzer(bus)
        for _ in range(20):
            analyzer.add_volume("ABCD", 100_000)

        result = analyzer.analyze("ABCD", 500_000)
        assert result.rvol == Decimal("5")


class TestVolumeZeroHandling:
    async def test_zero_volume_excluded(self, bus):
        analyzer = VolumeAnalyzer(bus)
        for _ in range(10):
            analyzer.add_volume("ABCD", 100_000)
        for _ in range(10):
            analyzer.add_volume("ABCD", 0)

        result = analyzer.analyze("ABCD", 100_000)
        assert result.active_days == 10
        assert result.zero_volume_days == 10

    async def test_low_activity_warning(self, bus):
        analyzer = VolumeAnalyzer(bus)
        for _ in range(5):
            analyzer.add_volume("ABCD", 100_000)
        for _ in range(15):
            analyzer.add_volume("ABCD", 0)

        result = analyzer.analyze("ABCD", 100_000)
        assert result.low_activity_warning is True

    async def test_insufficient_history(self, bus):
        analyzer = VolumeAnalyzer(bus)
        analyzer.add_volume("ABCD", 100_000)

        result = analyzer.analyze("ABCD", 200_000)
        assert result.anomaly_level == "NORMAL"
        assert result.zscore == Decimal("0")


class TestVolumeAlertPublishing:
    async def test_significant_publishes_alert(self, bus):
        alerts = []
        bus.subscribe(AlertEvent, _collector(alerts))

        analyzer = VolumeAnalyzer(bus)
        analyzer.start()
        for i in range(20):
            analyzer.add_volume("ABCD", 100_000 + (i * 1000))

        event = MarketDataEvent(
            ticker="ABCD",
            price=Decimal("0.0002"),
            bid=Decimal("0.0002"),
            ask=Decimal("0.0003"),
            volume=10_000_000,
        )
        await bus.publish(event)

        assert len(alerts) == 1
        assert alerts[0].alert_type == "VOLUME_ANOMALY"

    async def test_normal_no_alert(self, bus):
        alerts = []
        bus.subscribe(AlertEvent, _collector(alerts))

        analyzer = VolumeAnalyzer(bus)
        analyzer.start()
        for _ in range(20):
            analyzer.add_volume("ABCD", 100_000)

        event = MarketDataEvent(
            ticker="ABCD",
            price=Decimal("0.0002"),
            bid=Decimal("0.0002"),
            ask=Decimal("0.0003"),
            volume=100_000,
        )
        await bus.publish(event)

        assert len(alerts) == 0


# ===========================================================================
# Time & Sales Analyzer
# ===========================================================================


class TestTSClassification:
    async def test_bid_hit_counted(self, bus):
        analyzer = TSAnalyzer(bus)
        analyzer.start()

        trade = _trade_event(side="bid")
        await bus.publish(trade)

        result = analyzer.get_result("ABCD")
        assert result.bid_hits == 1
        assert result.ask_hits == 0

    async def test_ask_hit_counted(self, bus):
        analyzer = TSAnalyzer(bus)
        analyzer.start()

        trade = _trade_event(side="ask")
        await bus.publish(trade)

        result = analyzer.get_result("ABCD")
        assert result.ask_hits == 1

    async def test_buy_sell_ratio(self, bus):
        analyzer = TSAnalyzer(bus)
        analyzer.start()

        for _ in range(3):
            await bus.publish(_trade_event(side="ask"))
        await bus.publish(_trade_event(side="bid"))

        result = analyzer.get_result("ABCD")
        assert result.buy_sell_ratio == Decimal("3")
        assert result.is_bullish is True

    async def test_bearish_ratio(self, bus):
        analyzer = TSAnalyzer(bus)
        analyzer.start()

        await bus.publish(_trade_event(side="ask"))
        for _ in range(3):
            await bus.publish(_trade_event(side="bid"))

        result = analyzer.get_result("ABCD")
        assert result.is_bullish is False

    async def test_no_bid_hits_ratio(self, bus):
        analyzer = TSAnalyzer(bus)
        analyzer.start()

        await bus.publish(_trade_event(side="ask"))
        result = analyzer.get_result("ABCD")
        assert result.buy_sell_ratio == Decimal("Infinity")

    async def test_unknown_side(self, bus):
        analyzer = TSAnalyzer(bus)
        analyzer.start()

        await bus.publish(_trade_event(side="unknown"))
        result = analyzer.get_result("ABCD")
        assert result.unknown_trades == 1


class TestTSBlockDetection:
    async def test_block_trade_detected(self, bus):
        analyzer = TSAnalyzer(bus)
        now = datetime.now(UTC)

        # 5 trades at same price within 1 second
        for i in range(5):
            trade = _trade_event(
                price="0.0002",
                size=1_000_000,
                side="bid",
                ts=now + timedelta(milliseconds=i * 100),
            )
            await bus.publish(trade)  # won't work without start, use direct
            analyzer._trades.setdefault("ABCD", __import__("collections").deque(maxlen=500))
            analyzer._trades["ABCD"].append(trade)

        result = analyzer.analyze("ABCD")
        assert len(result.block_trades) == 1
        assert result.block_trades[0].fill_count == 5
        assert result.block_trades[0].total_size == 5_000_000

    async def test_no_block_different_prices(self, bus):
        analyzer = TSAnalyzer(bus)
        now = datetime.now(UTC)

        prices = ["0.0001", "0.0002", "0.0003", "0.0004"]
        for i, p in enumerate(prices):
            trade = _trade_event(price=p, ts=now + timedelta(milliseconds=i * 100))
            analyzer._trades.setdefault("ABCD", __import__("collections").deque(maxlen=500))
            analyzer._trades["ABCD"].append(trade)

        result = analyzer.analyze("ABCD")
        assert len(result.block_trades) == 0

    async def test_no_block_too_few_trades(self, bus):
        analyzer = TSAnalyzer(bus)
        now = datetime.now(UTC)

        for i in range(2):
            trade = _trade_event(price="0.0002", ts=now + timedelta(milliseconds=i * 100))
            analyzer._trades.setdefault("ABCD", __import__("collections").deque(maxlen=500))
            analyzer._trades["ABCD"].append(trade)

        result = analyzer.analyze("ABCD")
        assert len(result.block_trades) == 0


class TestTSMMTracking:
    async def test_recent_mm_ids(self, bus):
        analyzer = TSAnalyzer(bus)
        analyzer.start()

        await bus.publish(_trade_event(mm_id="NITE"))
        await bus.publish(_trade_event(mm_id="CSTI"))
        await bus.publish(_trade_event(mm_id="NITE"))

        result = analyzer.get_result("ABCD")
        # Should deduplicate while preserving order
        assert "NITE" in result.recent_mm_ids
        assert "CSTI" in result.recent_mm_ids


class TestTSReset:
    async def test_reset_clears(self, bus):
        analyzer = TSAnalyzer(bus)
        analyzer.start()

        await bus.publish(_trade_event())
        assert analyzer.get_result("ABCD") is not None

        analyzer.reset_symbol("ABCD")
        assert analyzer.get_result("ABCD") is None
        assert analyzer.get_trades("ABCD") == []


# ===========================================================================
# Dilution Sentinel
# ===========================================================================


class TestDilutionScoring:
    async def test_clear_no_signals(self, bus):
        l2 = L2Analyzer(bus)
        vol = VolumeAnalyzer(bus)
        ts = TSAnalyzer(bus)
        sentinel = DilutionSentinel(bus, l2, vol, ts)

        result = await sentinel.evaluate("ABCD")
        assert result.score == 0
        assert result.severity == "CLEAR"
        assert result.should_exit is False

    async def test_bad_mm_triggers_warning(self, bus):
        l2 = L2Analyzer(bus)
        vol = VolumeAnalyzer(bus)
        ts = TSAnalyzer(bus)
        sentinel = DilutionSentinel(bus, l2, vol, ts)

        # Set up L2 with bad MM on ask
        event = _l2_event(
            bids=(("0.0002", 1_000_000, "NITE"),),
            asks=(("0.0003", 500_000, "MAXM"),),
        )
        l2._results["ABCD"] = l2.analyze(event)

        result = await sentinel.evaluate("ABCD")
        assert result.score >= 4
        assert result.has_bad_mm is True
        assert result.should_exit is True  # score >= 3

    async def test_volume_spike_adds_points(self, bus):
        l2 = L2Analyzer(bus)
        vol = VolumeAnalyzer(bus)
        ts = TSAnalyzer(bus)
        sentinel = DilutionSentinel(bus, l2, vol, ts)

        # Set up volume with significant z-score
        from src.analysis.volume import VolumeAnalysis
        vol._results["ABCD"] = VolumeAnalysis(
            ticker="ABCD",
            current_volume=10_000_000,
            mean_volume=Decimal("100000"),
            std_volume=Decimal("10000"),
            zscore=Decimal("4.0"),
            rvol=Decimal("100"),
            anomaly_level="EXTREME",
            active_days=20,
            zero_volume_days=0,
            low_activity_warning=False,
        )

        result = await sentinel.evaluate("ABCD")
        assert result.score >= 3
        assert result.should_exit is True

    async def test_multiple_signals_accumulate(self, bus):
        l2 = L2Analyzer(bus)
        vol = VolumeAnalyzer(bus)
        ts = TSAnalyzer(bus)
        sentinel = DilutionSentinel(bus, l2, vol, ts)

        # Bad MM (+4) + volume spike (+3)
        event = _l2_event(
            bids=(("0.0002", 1_000_000, "NITE"),),
            asks=(("0.0003", 500_000, "MAXM"),),
        )
        l2._results["ABCD"] = l2.analyze(event)

        from src.analysis.volume import VolumeAnalysis
        vol._results["ABCD"] = VolumeAnalysis(
            ticker="ABCD",
            current_volume=10_000_000,
            mean_volume=Decimal("100000"),
            std_volume=Decimal("10000"),
            zscore=Decimal("4.0"),
            rvol=Decimal("100"),
            anomaly_level="EXTREME",
            active_days=20,
            zero_volume_days=0,
            low_activity_warning=False,
        )

        result = await sentinel.evaluate("ABCD")
        assert result.score >= 7
        assert result.severity == "CRITICAL"

    async def test_score_capped_at_10(self, bus):
        l2 = L2Analyzer(bus)
        vol = VolumeAnalyzer(bus)
        ts = TSAnalyzer(bus)
        sentinel = DilutionSentinel(bus, l2, vol, ts)

        # Stack all signals
        event = _l2_event(
            bids=(("0.0002", 1_000_000, "NITE"),),
            asks=(("0.0003", 500_000, "MAXM"),),
        )
        l2._results["ABCD"] = l2.analyze(event)

        from src.analysis.volume import VolumeAnalysis
        vol._results["ABCD"] = VolumeAnalysis(
            ticker="ABCD",
            current_volume=10_000_000,
            mean_volume=Decimal("100000"),
            std_volume=Decimal("10000"),
            zscore=Decimal("4.0"),
            rvol=Decimal("100"),
            anomaly_level="EXTREME",
            active_days=20,
            zero_volume_days=0,
            low_activity_warning=False,
        )

        # Set up T&S with block trades on bid and low ratio
        from src.analysis.time_sales import BlockTrade, TSAnalysis
        now = datetime.now(UTC)
        ts._results["ABCD"] = TSAnalysis(
            ticker="ABCD",
            total_trades=10,
            bid_hits=8,
            ask_hits=1,
            unknown_trades=1,
            buy_sell_ratio=Decimal("0.125"),
            is_bullish=False,
            block_trades=(BlockTrade(
                price=Decimal("0.0002"),
                total_size=5_000_000,
                fill_count=5,
                side="bid",
                timestamp=now,
            ),),
        )

        result = await sentinel.evaluate("ABCD")
        assert result.score == 10


class TestDilutionSeverityClassification:
    async def test_clear(self, bus):
        sentinel = DilutionSentinel(bus, L2Analyzer(bus), VolumeAnalyzer(bus), TSAnalyzer(bus))
        assert sentinel._classify_severity(0) == "CLEAR"
        assert sentinel._classify_severity(2) == "CLEAR"

    async def test_warning(self, bus):
        sentinel = DilutionSentinel(bus, L2Analyzer(bus), VolumeAnalyzer(bus), TSAnalyzer(bus))
        assert sentinel._classify_severity(3) == "WARNING"
        assert sentinel._classify_severity(4) == "WARNING"

    async def test_high_alert(self, bus):
        sentinel = DilutionSentinel(bus, L2Analyzer(bus), VolumeAnalyzer(bus), TSAnalyzer(bus))
        assert sentinel._classify_severity(5) == "HIGH_ALERT"
        assert sentinel._classify_severity(6) == "HIGH_ALERT"

    async def test_critical(self, bus):
        sentinel = DilutionSentinel(bus, L2Analyzer(bus), VolumeAnalyzer(bus), TSAnalyzer(bus))
        assert sentinel._classify_severity(7) == "CRITICAL"
        assert sentinel._classify_severity(10) == "CRITICAL"


class TestDilutionAlertPublishing:
    async def test_warning_publishes_alert(self, bus):
        alerts = []
        bus.subscribe(DilutionAlertEvent, _collector(alerts))

        l2 = L2Analyzer(bus)
        sentinel = DilutionSentinel(bus, l2, VolumeAnalyzer(bus), TSAnalyzer(bus))

        event = _l2_event(
            bids=(("0.0002", 1_000_000, "NITE"),),
            asks=(("0.0003", 500_000, "MAXM"),),
        )
        l2._results["ABCD"] = l2.analyze(event)

        await sentinel.evaluate("ABCD")
        assert len(alerts) == 1
        assert alerts[0].severity == "WARNING" or alerts[0].severity == "HIGH_ALERT"

    async def test_clear_no_alert(self, bus):
        alerts = []
        bus.subscribe(DilutionAlertEvent, _collector(alerts))

        sentinel = DilutionSentinel(
            bus, L2Analyzer(bus), VolumeAnalyzer(bus), TSAnalyzer(bus)
        )
        await sentinel.evaluate("ABCD")
        assert len(alerts) == 0


class TestDilutionBidErosion:
    async def test_bid_erosion_detected(self, bus):
        l2 = L2Analyzer(bus)
        sentinel = DilutionSentinel(
            bus, l2, VolumeAnalyzer(bus), TSAnalyzer(bus)
        )

        # First evaluation: high imbalance
        event1 = _l2_event(
            bids=(("0.0002", 5_000_000, "NITE"),),
            asks=(("0.0003", 500_000, "CSTI"),),
        )
        l2._results["ABCD"] = l2.analyze(event1)
        await sentinel.evaluate("ABCD")

        # Second evaluation: imbalance drops by > 30%
        event2 = _l2_event(
            bids=(("0.0002", 1_000_000, "NITE"),),
            asks=(("0.0003", 500_000, "CSTI"),),
        )
        l2._results["ABCD"] = l2.analyze(event2)
        result = await sentinel.evaluate("ABCD")

        erosion_signals = [s for s in result.signals if "erosion" in s.lower()]
        assert len(erosion_signals) > 0
