"""Tests for src/core/event_bus.py — subscribe, publish, error isolation."""

from decimal import Decimal

from src.core.event_bus import EventBus
from src.core.events import AlertEvent, MarketDataEvent


async def test_subscribe_and_publish(event_bus: EventBus):
    received = []

    async def handler(event: MarketDataEvent):
        received.append(event)

    event_bus.subscribe(MarketDataEvent, handler)

    event = MarketDataEvent(
        ticker="ABCD", price=Decimal("0.0003"), bid=Decimal("0.0003"),
        ask=Decimal("0.0004"), volume=100_000,
    )
    await event_bus.publish(event)

    assert len(received) == 1
    assert received[0].ticker == "ABCD"


async def test_multiple_handlers(event_bus: EventBus):
    results = []

    async def handler_a(event):
        results.append("a")

    async def handler_b(event):
        results.append("b")

    event_bus.subscribe(MarketDataEvent, handler_a)
    event_bus.subscribe(MarketDataEvent, handler_b)

    event = MarketDataEvent(
        ticker="ABCD", price=Decimal("0.0003"), bid=Decimal("0.0003"),
        ask=Decimal("0.0004"), volume=100_000,
    )
    await event_bus.publish(event)

    assert "a" in results
    assert "b" in results
    assert len(results) == 2


async def test_type_matching(event_bus: EventBus):
    """Handlers only fire for their registered event type."""
    received = []

    async def handler(event):
        received.append(event)

    event_bus.subscribe(AlertEvent, handler)

    # Publish a MarketDataEvent — should NOT trigger AlertEvent handler
    event = MarketDataEvent(
        ticker="ABCD", price=Decimal("0.0003"), bid=Decimal("0.0003"),
        ask=Decimal("0.0004"), volume=100_000,
    )
    await event_bus.publish(event)

    assert len(received) == 0


async def test_error_isolation(event_bus: EventBus):
    """A failing handler does not prevent other handlers from running."""
    results = []

    async def bad_handler(event):
        raise RuntimeError("boom")

    async def good_handler(event):
        results.append("ok")

    event_bus.subscribe(MarketDataEvent, bad_handler)
    event_bus.subscribe(MarketDataEvent, good_handler)

    event = MarketDataEvent(
        ticker="ABCD", price=Decimal("0.0003"), bid=Decimal("0.0003"),
        ask=Decimal("0.0004"), volume=100_000,
    )
    await event_bus.publish(event)

    assert results == ["ok"]


async def test_publish_no_handlers(event_bus: EventBus):
    """Publishing with no subscribers should not raise."""
    event = MarketDataEvent(
        ticker="ABCD", price=Decimal("0.0003"), bid=Decimal("0.0003"),
        ask=Decimal("0.0004"), volume=100_000,
    )
    await event_bus.publish(event)  # Should not raise


async def test_reset(event_bus: EventBus):
    received = []

    async def handler(event):
        received.append(event)

    event_bus.subscribe(MarketDataEvent, handler)
    event_bus.reset()

    event = MarketDataEvent(
        ticker="ABCD", price=Decimal("0.0003"), bid=Decimal("0.0003"),
        ask=Decimal("0.0004"), volume=100_000,
    )
    await event_bus.publish(event)

    assert len(received) == 0
