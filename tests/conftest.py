"""Shared test fixtures: in-memory DB, session factory, event bus."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.event_bus import EventBus
from src.database.schema import Base


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def event_bus():
    bus = EventBus()
    yield bus
    bus.reset()
