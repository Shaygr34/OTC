"""Tests for scanner methods on broker adapters."""

import pytest

from src.broker.mock import MockAdapter
from src.core.event_bus import EventBus


@pytest.fixture
def adapter():
    bus = EventBus()
    return MockAdapter(bus)


@pytest.mark.asyncio
async def test_request_scanner_returns_list(adapter):
    await adapter.connect()
    results = await adapter.request_scanner(None)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_request_scanner_with_injected_data(adapter):
    await adapter.connect()
    adapter.set_scanner_results([
        {"symbol": "APTY", "exchange": "PINK"},
        {"symbol": "MWWC", "exchange": "PINK"},
    ])
    results = await adapter.request_scanner(None)
    assert len(results) == 2
    assert results[0]["symbol"] == "APTY"


@pytest.mark.asyncio
async def test_get_scanner_parameters(adapter):
    await adapter.connect()
    params = await adapter.get_scanner_parameters()
    assert isinstance(params, str)
