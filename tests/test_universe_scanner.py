"""Tests for UniverseScanner — OTC universe discovery."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from config.settings import ScannerSettings
from src.broker.mock import MockAdapter
from src.core.event_bus import EventBus
from src.database.repository import Repository, get_engine, get_session_factory
from src.database.schema import create_all_tables
from src.scanner.universe import UniverseScanner


@dataclass
class MockContractDetails:
    contract: MagicMock
    validExchanges: str = ""


@dataclass
class MockScanData:
    rank: int
    contractDetails: MockContractDetails
    distance: str = ""
    benchmark: str = ""
    projection: str = ""
    legsStr: str = ""


def _make_scan_result(symbol: str, exchange: str = "PINK") -> MockScanData:
    contract = MagicMock()
    contract.symbol = symbol
    contract.exchange = "SMART"
    contract.primaryExchange = exchange
    details = MockContractDetails(
        contract=contract,
        validExchanges=f"SMART,{exchange}",
    )
    return MockScanData(rank=0, contractDetails=details)


@pytest.fixture
async def scanner():
    bus = EventBus()
    adapter = MockAdapter(bus)
    await adapter.connect()
    engine = get_engine("sqlite+aiosqlite://")
    session_factory = get_session_factory(engine)
    await create_all_tables(engine)
    repo = Repository(session_factory)
    settings = ScannerSettings(enabled=True, interval_minutes=15, max_results_per_scan=50)
    s = UniverseScanner(adapter=adapter, repo=repo, settings=settings)
    yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_scan_once_inserts_new_candidates(scanner):
    """Scanner should insert new tickers as active candidates."""
    scanner._adapter.set_scanner_results([
        _make_scan_result("APTY", "PINK"),
        _make_scan_result("NEWT", "PINK"),
    ])
    count = await scanner.scan_once()
    assert count == 2

    candidate = await scanner._repo.get_candidate_by_ticker("APTY")
    assert candidate is not None
    assert candidate.status == "active"


@pytest.mark.asyncio
async def test_scan_once_skips_existing_candidates(scanner):
    """Scanner should not duplicate existing candidates."""
    await scanner._repo.upsert_candidate("APTY", "TRIPS", "active", "PINK")

    scanner._adapter.set_scanner_results([
        _make_scan_result("APTY", "PINK"),
        _make_scan_result("NEWT", "PINK"),
    ])
    count = await scanner.scan_once()
    assert count == 1  # Only NEWT


@pytest.mark.asyncio
async def test_scan_once_filters_non_otc_exchanges(scanner):
    """Scanner should reject tickers not on PINK/GREY."""
    scanner._adapter.set_scanner_results([
        _make_scan_result("AAPL", "NASDAQ"),
        _make_scan_result("NEWT", "PINK"),
    ])
    count = await scanner.scan_once()
    assert count == 1  # Only NEWT


@pytest.mark.asyncio
async def test_scan_once_handles_empty_results(scanner):
    """Scanner should handle zero results gracefully."""
    scanner._adapter.set_scanner_results([])
    count = await scanner.scan_once()
    assert count == 0


@pytest.mark.asyncio
async def test_start_stop(scanner):
    """Scanner loop should start and stop cleanly."""
    await scanner.start()
    assert scanner._running
    await scanner.stop()
    assert not scanner._running
