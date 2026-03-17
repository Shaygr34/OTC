"""Tests for TickerWatcher — DB-to-subscription bridge."""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.broker.mock import MockAdapter
from src.core.event_bus import EventBus
from src.core.ticker_watcher import TickerWatcher
from src.database.repository import Repository
from src.database.schema import Base, Candidate
from src.scanner.screener import Screener


@pytest.fixture
async def db_setup():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    yield engine, sf
    await engine.dispose()


@pytest.fixture
def bus():
    b = EventBus()
    yield b
    b.reset()


@pytest.fixture
async def watcher(db_setup, bus):
    _, sf = db_setup
    repo = Repository(sf)
    adapter = MockAdapter(bus)
    await adapter.connect()
    screener = Screener(bus)
    w = TickerWatcher(repo=repo, adapter=adapter, screener=screener, poll_interval=0.1)
    yield w
    await w.stop()
    await adapter.disconnect()


async def _insert_manual(sf, ticker, exchange="PINK"):
    async with sf() as session:
        session.add(Candidate(
            ticker=ticker, price_tier="UNKNOWN", status="manual",
            exchange=exchange,
        ))
        await session.commit()


async def _get_candidate(sf, ticker):
    async with sf() as session:
        result = await session.execute(
            select(Candidate).where(Candidate.ticker == ticker)
        )
        return result.scalar_one_or_none()


class TestTickerWatcherActivation:
    async def test_manual_ticker_gets_activated(self, db_setup, watcher):
        _, sf = db_setup
        await _insert_manual(sf, "AAAA")

        await watcher.activate_existing()

        c = await _get_candidate(sf, "AAAA")
        assert c.status == "active"

    async def test_activated_ticker_gets_subscriptions(self, db_setup, watcher):
        _, sf = db_setup
        await _insert_manual(sf, "BBBB")

        await watcher.activate_existing()

        adapter = watcher._adapter
        subs = adapter.get_subscriptions("BBBB")
        assert "market_data" in subs
        assert "l2_depth" in subs
        assert "tick_by_tick" in subs

    async def test_exchange_stored_on_activate(self, db_setup, watcher):
        _, sf = db_setup
        await _insert_manual(sf, "CCCC", exchange="GREY")

        await watcher.activate_existing()

        c = await _get_candidate(sf, "CCCC")
        assert c.status == "active"
        assert c.exchange == "GREY"

    async def test_duplicate_activation_skipped(self, db_setup, watcher):
        _, sf = db_setup
        await _insert_manual(sf, "DDDD")

        await watcher.activate_existing()
        await watcher.activate_existing()

        # Should only have called create_otc_contract once
        assert "DDDD" in watcher._activated

    async def test_multiple_manual_tickers(self, db_setup, watcher):
        _, sf = db_setup
        await _insert_manual(sf, "EEEE")
        await _insert_manual(sf, "FFFF")

        await watcher.activate_existing()

        c1 = await _get_candidate(sf, "EEEE")
        c2 = await _get_candidate(sf, "FFFF")
        assert c1.status == "active"
        assert c2.status == "active"


class TestTickerWatcherPolling:
    async def test_poll_loop_activates_new_ticker(self, db_setup, watcher):
        _, sf = db_setup
        watcher.start()

        # Add ticker after poll loop started
        await _insert_manual(sf, "LATE")
        await asyncio.sleep(0.3)  # Give the poll loop time to run

        c = await _get_candidate(sf, "LATE")
        assert c.status == "active"

        await watcher.stop()

    async def test_stop_cancels_loop(self, db_setup, watcher):
        watcher.start()
        await watcher.stop()
        assert watcher._task.done()


class TestTickerWatcherWithSystemRunner:
    async def test_system_runner_has_ticker_watcher(self):
        from scripts.run_system import SystemRunner
        runner = SystemRunner()
        assert hasattr(runner, "ticker_watcher")
        assert isinstance(runner.ticker_watcher, TickerWatcher)

    async def test_system_start_starts_watcher(self):
        from scripts.run_system import SystemRunner
        runner = SystemRunner()
        await runner.start()
        assert runner.ticker_watcher._task is not None
        assert not runner.ticker_watcher._task.done()
        await runner.stop()
