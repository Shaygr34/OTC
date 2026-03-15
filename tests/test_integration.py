"""Integration tests — end-to-end with MockAdapter, DB, and watchlist."""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.broker.history import HistoryLoader
from src.broker.mock import MockAdapter
from src.core.event_bus import EventBus
from src.database.persistence import PersistenceSubscriber
from src.database.repository import Repository
from src.database.schema import Base, L2SnapshotRow, TradeRow
from src.scanner.screener import Screener
from src.scanner.watchlist import WatchlistEntry, load_watchlist

# ── Watchlist loading ──


def test_load_watchlist_from_yaml(tmp_path):
    yaml_file = tmp_path / "watchlist.yaml"
    yaml_file.write_text(
        "symbols:\n"
        "  - ticker: ABCD\n"
        "    exchange: PINK\n"
        "  - ticker: EFGH\n"
        "    exchange: GREY\n"
    )
    entries = load_watchlist(yaml_file)
    assert len(entries) == 2
    assert entries[0] == WatchlistEntry(ticker="ABCD", exchange="PINK")
    assert entries[1] == WatchlistEntry(ticker="EFGH", exchange="GREY")


def test_load_watchlist_missing_file():
    entries = load_watchlist("/nonexistent/path.yaml")
    assert entries == []


def test_load_watchlist_empty_symbols(tmp_path):
    yaml_file = tmp_path / "watchlist.yaml"
    yaml_file.write_text("symbols:\n")
    entries = load_watchlist(yaml_file)
    assert entries == []


def test_load_watchlist_normalizes_case(tmp_path):
    yaml_file = tmp_path / "watchlist.yaml"
    yaml_file.write_text("symbols:\n  - ticker: abcd\n    exchange: pink\n")
    entries = load_watchlist(yaml_file)
    assert entries[0].ticker == "ABCD"
    assert entries[0].exchange == "PINK"


def test_load_watchlist_default_exchange(tmp_path):
    yaml_file = tmp_path / "watchlist.yaml"
    yaml_file.write_text("symbols:\n  - ticker: ZZZZ\n")
    entries = load_watchlist(yaml_file)
    assert entries[0].exchange == "PINK"


# ── History seeder ──


async def test_history_seeder_with_mock():
    bus = EventBus()
    adapter = MockAdapter(bus)
    screener = Screener(bus)
    await adapter.connect()

    bars = [
        {
            "open": Decimal("0.0003"),
            "high": Decimal("0.0004"),
            "low": Decimal("0.0002"),
            "close": Decimal("0.0003"),
            "volume": 50000,
        }
        for _ in range(20)
    ]
    adapter.set_historical_data("ABCD", bars)

    watchlist = [WatchlistEntry(ticker="ABCD", exchange="PINK")]
    loaded = await HistoryLoader.seed(watchlist, adapter, screener)

    assert loaded["ABCD"] == 20
    assert len(screener.get_bars("ABCD")) == 20
    await adapter.disconnect()


async def test_history_seeder_empty_watchlist():
    bus = EventBus()
    adapter = MockAdapter(bus)
    screener = Screener(bus)
    await adapter.connect()

    loaded = await HistoryLoader.seed([], adapter, screener)
    assert loaded == {}
    await adapter.disconnect()


async def test_history_seeder_no_data():
    bus = EventBus()
    adapter = MockAdapter(bus)
    screener = Screener(bus)
    await adapter.connect()

    watchlist = [WatchlistEntry(ticker="NODATA", exchange="PINK")]
    loaded = await HistoryLoader.seed(watchlist, adapter, screener)

    assert loaded["NODATA"] == 0
    assert len(screener.get_bars("NODATA")) == 0
    await adapter.disconnect()


# ── End-to-end: events → DB ──


async def test_e2e_push_events_verify_db():
    """Push events through MockAdapter → verify rows land in SQLite."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)

    bus = EventBus()
    repo = Repository(sf)
    persistence = PersistenceSubscriber(repo, bus)
    persistence.start()

    adapter = MockAdapter(bus)
    await adapter.connect()

    # Push L2 update
    await adapter.push_l2_update(
        "TEST",
        bid_levels=((Decimal("0.0003"), 100000, "ETRF"),),
        ask_levels=((Decimal("0.0004"), 50000, "NITE"),),
    )

    # Push trade
    await adapter.push_trade("TEST", Decimal("0.0003"), 10000, side="ask")

    # Verify L2 snapshot in DB
    async with sf() as session:
        l2_rows = (await session.execute(select(L2SnapshotRow))).scalars().all()
        assert len(l2_rows) == 1
        assert l2_rows[0].ticker == "TEST"

    # Verify trade in DB
    async with sf() as session:
        trade_rows = (await session.execute(select(TradeRow))).scalars().all()
        assert len(trade_rows) == 1
        assert trade_rows[0].ticker == "TEST"
        assert trade_rows[0].price == "0.0003"

    await adapter.disconnect()
    await engine.dispose()


# ── Mock adapter historical bars ──


async def test_mock_adapter_request_historical_bars():
    bus = EventBus()
    adapter = MockAdapter(bus)
    await adapter.connect()

    # Default: empty
    bars = await adapter.request_historical_bars("ABCD")
    assert bars == []

    # Set test data
    test_bars = [{"open": Decimal("1"), "high": Decimal("2"), "low": Decimal("0.5"),
                  "close": Decimal("1.5"), "volume": 1000}]
    adapter.set_historical_data("ABCD", test_bars)

    bars = await adapter.request_historical_bars("ABCD")
    assert len(bars) == 1
    assert bars[0]["close"] == Decimal("1.5")

    await adapter.disconnect()


async def test_mock_adapter_historical_bars_not_connected():
    bus = EventBus()
    adapter = MockAdapter(bus)
    with pytest.raises(ConnectionError):
        await adapter.request_historical_bars("ABCD")
