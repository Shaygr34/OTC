"""Tests for the broker adapter layer (MockAdapter).

Covers lifecycle, contracts, data flow, subscription tracking,
and event isolation — all without requiring a running TWS instance.
"""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from src.broker.adapter import BrokerAdapter
from src.broker.mock import MockAdapter, MockContract
from src.core.event_bus import EventBus
from src.core.events import L2UpdateEvent, MarketDataEvent, TradeEvent


@pytest.fixture
def bus():
    b = EventBus()
    yield b
    b.reset()


@pytest.fixture
def adapter(bus):
    return MockAdapter(bus)


def _collector(target: list):
    """Return an async handler that appends events to *target*."""

    async def _handler(event):
        target.append(event)

    return _handler


# ── ABC conformance ──────────────────────────────────────────────


class TestMockAdapterIsABrokerAdapter:
    def test_isinstance(self, adapter):
        assert isinstance(adapter, BrokerAdapter)

    def test_has_all_abstract_methods(self):
        """BrokerAdapter's abstract methods are all present on MockAdapter."""
        abstract_names = {
            "connect",
            "disconnect",
            "is_connected",
            "create_otc_contract",
            "subscribe_market_data",
            "unsubscribe_market_data",
            "subscribe_l2_depth",
            "unsubscribe_l2_depth",
            "subscribe_tick_by_tick",
            "unsubscribe_tick_by_tick",
        }
        for name in abstract_names:
            assert hasattr(MockAdapter, name), f"Missing method: {name}"


# ── Lifecycle ────────────────────────────────────────────────────


class TestLifecycle:
    async def test_starts_disconnected(self, adapter):
        assert adapter.is_connected() is False

    async def test_connect_disconnect(self, adapter):
        await adapter.connect()
        assert adapter.is_connected() is True
        await adapter.disconnect()
        assert adapter.is_connected() is False

    async def test_subscribe_before_connect_raises(self, adapter):
        with pytest.raises(ConnectionError):
            await adapter.subscribe_market_data("ABCD", "PINK")

    async def test_push_before_connect_raises(self, adapter):
        with pytest.raises(ConnectionError):
            await adapter.push_market_data(
                "ABCD", Decimal("0.0001"), Decimal("0.0001"), Decimal("0.0002"), 1000
            )

    async def test_create_contract_before_connect_raises(self, adapter):
        with pytest.raises(ConnectionError):
            await adapter.create_otc_contract("ABCD")

    async def test_disconnect_clears_subscriptions(self, adapter):
        await adapter.connect()
        await adapter.subscribe_market_data("ABCD", "PINK")
        await adapter.subscribe_l2_depth("EFGH", "GREY")
        await adapter.disconnect()
        assert adapter.get_subscriptions("ABCD") == set()
        assert adapter.get_subscriptions("EFGH") == set()


# ── Contract creation ────────────────────────────────────────────


class TestContractCreation:
    async def test_pink_contract(self, adapter):
        await adapter.connect()
        contract = await adapter.create_otc_contract("ABCD", "PINK")
        assert isinstance(contract, MockContract)
        assert contract.symbol == "ABCD"
        assert contract.exchange == "PINK"
        assert contract.currency == "USD"

    async def test_grey_contract(self, adapter):
        await adapter.connect()
        contract = await adapter.create_otc_contract("EFGH", "GREY")
        assert contract.exchange == "GREY"

    async def test_default_exchange_is_pink(self, adapter):
        await adapter.connect()
        contract = await adapter.create_otc_contract("ABCD")
        assert contract.exchange == "PINK"

    async def test_case_insensitive_exchange(self, adapter):
        await adapter.connect()
        contract = await adapter.create_otc_contract("ABCD", "pink")
        assert contract.exchange == "PINK"

    async def test_invalid_exchange_raises(self, adapter):
        await adapter.connect()
        with pytest.raises(ValueError, match="Invalid OTC exchange"):
            await adapter.create_otc_contract("ABCD", "NYSE")

    async def test_contract_caching(self, adapter):
        await adapter.connect()
        c1 = await adapter.create_otc_contract("ABCD", "PINK")
        c2 = await adapter.create_otc_contract("ABCD", "PINK")
        assert c1 is c2

    async def test_unique_con_ids(self, adapter):
        await adapter.connect()
        c1 = await adapter.create_otc_contract("ABCD")
        c2 = await adapter.create_otc_contract("EFGH")
        assert c1.con_id != c2.con_id


# ── Market data flow ─────────────────────────────────────────────


class TestMarketDataFlow:
    async def test_push_market_data_received(self, adapter, bus):
        received = []
        bus.subscribe(MarketDataEvent, _collector(received))

        await adapter.connect()
        await adapter.push_market_data(
            "ABCD", Decimal("0.0003"), Decimal("0.0002"), Decimal("0.0004"), 5_000_000
        )

        assert len(received) == 1
        event = received[0]
        assert event.ticker == "ABCD"
        assert event.price == Decimal("0.0003")
        assert event.bid == Decimal("0.0002")
        assert event.ask == Decimal("0.0004")
        assert event.volume == 5_000_000

    async def test_market_data_event_is_frozen(self, adapter, bus):
        received = []
        bus.subscribe(MarketDataEvent, _collector(received))

        await adapter.connect()
        await adapter.push_market_data(
            "ABCD", Decimal("0.0001"), Decimal("0.0001"), Decimal("0.0002"), 1000
        )

        with pytest.raises(FrozenInstanceError):
            received[0].price = Decimal("999")

    async def test_market_data_has_timestamp(self, adapter, bus):
        received = []
        bus.subscribe(MarketDataEvent, _collector(received))

        await adapter.connect()
        await adapter.push_market_data(
            "ABCD", Decimal("0.0001"), Decimal("0.0001"), Decimal("0.0002"), 1000
        )

        assert received[0].timestamp is not None


# ── L2 update flow ───────────────────────────────────────────────


class TestL2UpdateFlow:
    async def test_push_l2_update_received(self, adapter, bus):
        received = []
        bus.subscribe(L2UpdateEvent, _collector(received))

        bid_levels = (
            (Decimal("0.0002"), 1_000_000, "NITE"),
            (Decimal("0.0001"), 500_000, "CSTI"),
        )
        ask_levels = (
            (Decimal("0.0003"), 200_000, "MAXM"),
        )

        await adapter.connect()
        await adapter.push_l2_update("ABCD", bid_levels, ask_levels)

        assert len(received) == 1
        event = received[0]
        assert event.ticker == "ABCD"
        assert len(event.bid_levels) == 2
        assert len(event.ask_levels) == 1

    async def test_l2_mm_ids_preserved(self, adapter, bus):
        received = []
        bus.subscribe(L2UpdateEvent, _collector(received))

        bid_levels = ((Decimal("0.0002"), 1_000_000, "NITE"),)
        ask_levels = ((Decimal("0.0003"), 200_000, "MAXM"),)

        await adapter.connect()
        await adapter.push_l2_update("ABCD", bid_levels, ask_levels)

        event = received[0]
        assert event.bid_levels[0][2] == "NITE"
        assert event.ask_levels[0][2] == "MAXM"

    async def test_l2_decimal_precision(self, adapter, bus):
        received = []
        bus.subscribe(L2UpdateEvent, _collector(received))

        bid_levels = ((Decimal("0.00015"), 1_000_000, "NITE"),)
        ask_levels = ((Decimal("0.00025"), 500_000, "CSTI"),)

        await adapter.connect()
        await adapter.push_l2_update("ABCD", bid_levels, ask_levels)

        event = received[0]
        assert event.bid_levels[0][0] == Decimal("0.00015")
        assert event.ask_levels[0][0] == Decimal("0.00025")


# ── Trade event flow ─────────────────────────────────────────────


class TestTradeEventFlow:
    async def test_push_trade_received(self, adapter, bus):
        received = []
        bus.subscribe(TradeEvent, _collector(received))

        await adapter.connect()
        await adapter.push_trade(
            "ABCD", Decimal("0.0002"), 500_000, side="bid", mm_id="NITE"
        )

        assert len(received) == 1
        event = received[0]
        assert event.ticker == "ABCD"
        assert event.price == Decimal("0.0002")
        assert event.size == 500_000
        assert event.side == "bid"
        assert event.mm_id == "NITE"

    async def test_trade_defaults(self, adapter, bus):
        received = []
        bus.subscribe(TradeEvent, _collector(received))

        await adapter.connect()
        await adapter.push_trade("ABCD", Decimal("0.0001"), 100_000)

        event = received[0]
        assert event.side == "unknown"
        assert event.mm_id == ""

    async def test_trade_ask_side(self, adapter, bus):
        received = []
        bus.subscribe(TradeEvent, _collector(received))

        await adapter.connect()
        await adapter.push_trade("ABCD", Decimal("0.0003"), 200_000, side="ask")

        assert received[0].side == "ask"


# ── Subscription tracking ────────────────────────────────────────


class TestSubscriptionTracking:
    async def test_subscribe_tracks_type(self, adapter):
        await adapter.connect()
        await adapter.subscribe_market_data("ABCD", "PINK")
        assert "market_data" in adapter.get_subscriptions("ABCD")

    async def test_multiple_sub_types(self, adapter):
        await adapter.connect()
        await adapter.subscribe_market_data("ABCD", "PINK")
        await adapter.subscribe_l2_depth("ABCD", "PINK")
        await adapter.subscribe_tick_by_tick("ABCD", "PINK")
        subs = adapter.get_subscriptions("ABCD")
        assert subs == {"market_data", "l2_depth", "tick_by_tick"}

    async def test_unsubscribe_removes_type(self, adapter):
        await adapter.connect()
        await adapter.subscribe_market_data("ABCD", "PINK")
        await adapter.subscribe_l2_depth("ABCD", "PINK")
        await adapter.unsubscribe_market_data("ABCD")
        assert adapter.get_subscriptions("ABCD") == {"l2_depth"}

    async def test_unsubscribe_all_clears_symbol(self, adapter):
        await adapter.connect()
        await adapter.subscribe_market_data("ABCD", "PINK")
        await adapter.unsubscribe_market_data("ABCD")
        assert adapter.get_subscriptions("ABCD") == set()

    async def test_disconnect_clears_all_subscriptions(self, adapter):
        await adapter.connect()
        await adapter.subscribe_market_data("ABCD", "PINK")
        await adapter.subscribe_l2_depth("EFGH", "GREY")
        await adapter.subscribe_tick_by_tick("IJKL", "PINK")
        await adapter.disconnect()
        assert adapter.get_subscriptions("ABCD") == set()
        assert adapter.get_subscriptions("EFGH") == set()
        assert adapter.get_subscriptions("IJKL") == set()

    async def test_get_subscriptions_returns_copy(self, adapter):
        await adapter.connect()
        await adapter.subscribe_market_data("ABCD", "PINK")
        subs = adapter.get_subscriptions("ABCD")
        subs.add("hacked")
        assert "hacked" not in adapter.get_subscriptions("ABCD")


# ── Event isolation ──────────────────────────────────────────────


class TestEventIsolation:
    async def test_multiple_handlers_receive_same_event(self, adapter, bus):
        received_a = []
        received_b = []
        bus.subscribe(MarketDataEvent, _collector(received_a))
        bus.subscribe(MarketDataEvent, _collector(received_b))

        await adapter.connect()
        await adapter.push_market_data(
            "ABCD", Decimal("0.0001"), Decimal("0.0001"), Decimal("0.0002"), 1000
        )

        assert len(received_a) == 1
        assert len(received_b) == 1
        assert received_a[0] is received_b[0]

    async def test_different_event_types_independent(self, adapter, bus):
        market_events = []
        trade_events = []
        bus.subscribe(MarketDataEvent, _collector(market_events))
        bus.subscribe(TradeEvent, _collector(trade_events))

        await adapter.connect()
        await adapter.push_market_data(
            "ABCD", Decimal("0.0001"), Decimal("0.0001"), Decimal("0.0002"), 1000
        )
        await adapter.push_trade("ABCD", Decimal("0.0001"), 100_000)

        assert len(market_events) == 1
        assert len(trade_events) == 1
        assert isinstance(market_events[0], MarketDataEvent)
        assert isinstance(trade_events[0], TradeEvent)

    async def test_l2_events_do_not_trigger_market_data_handlers(self, adapter, bus):
        market_events = []
        bus.subscribe(MarketDataEvent, _collector(market_events))

        await adapter.connect()
        await adapter.push_l2_update(
            "ABCD",
            ((Decimal("0.0001"), 1000, "NITE"),),
            ((Decimal("0.0002"), 500, "MAXM"),),
        )

        assert len(market_events) == 0
