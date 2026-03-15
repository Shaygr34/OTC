"""Async repository for CRUD operations on the ATM database."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.database.schema import (
    Alert,
    Candidate,
    DailyScore,
    L2SnapshotRow,
    TradeLog,
    TradeRow,
)


def get_engine(url: str = "sqlite+aiosqlite:///data/atm.db") -> AsyncEngine:
    """Create an async SQLAlchemy engine."""
    return create_async_engine(url, echo=False)


def get_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a session factory bound to the given engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


class Repository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # -- Candidates ----------------------------------------------------------

    async def add_candidate(
        self,
        ticker: str,
        price_tier: str,
        atm_score: Decimal | None = None,
        status: str = "active",
    ) -> Candidate:
        async with self._session_factory() as session:
            candidate = Candidate(
                ticker=ticker,
                price_tier=price_tier,
                first_seen=datetime.now(UTC),
                atm_score=str(atm_score) if atm_score is not None else None,
                status=status,
            )
            session.add(candidate)
            await session.commit()
            await session.refresh(candidate)
            return candidate

    async def get_candidates_by_status(self, status: str) -> list[Candidate]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Candidate).where(Candidate.status == status)
            )
            return list(result.scalars().all())

    # -- L2 Snapshots --------------------------------------------------------

    async def save_l2_snapshot(
        self,
        ticker: str,
        timestamp: datetime,
        bid_levels: list[dict],
        ask_levels: list[dict],
        imbalance_ratio: Decimal | None = None,
        total_bid_shares: int | None = None,
        total_ask_shares: int | None = None,
    ) -> L2SnapshotRow:
        async with self._session_factory() as session:
            row = L2SnapshotRow(
                ticker=ticker,
                timestamp=timestamp,
                bid_levels=bid_levels,
                ask_levels=ask_levels,
                imbalance_ratio=str(imbalance_ratio) if imbalance_ratio is not None else None,
                total_bid_shares=total_bid_shares,
                total_ask_shares=total_ask_shares,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    # -- Trades --------------------------------------------------------------

    async def save_trade(
        self,
        ticker: str,
        timestamp: datetime,
        price: Decimal,
        size: int,
        side: str | None = None,
        mm_id: str | None = None,
    ) -> TradeRow:
        async with self._session_factory() as session:
            row = TradeRow(
                ticker=ticker,
                timestamp=timestamp,
                price=str(price),
                size=size,
                side=side,
                mm_id=mm_id,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    # -- Trade Log -----------------------------------------------------------

    async def log_trade(
        self,
        ticker: str,
        entry_price: Decimal,
        shares: int,
        **kwargs,
    ) -> TradeLog:
        async with self._session_factory() as session:
            # Convert any Decimal kwargs to str for TEXT columns
            str_fields = {
                "exit_price", "position_pct", "portfolio_value_at_entry",
                "l2_ratio_at_entry", "atm_score_at_entry", "pnl_usd", "pnl_pct",
            }
            processed = {}
            for k, v in kwargs.items():
                if k in str_fields and v is not None:
                    processed[k] = str(v)
                else:
                    processed[k] = v

            row = TradeLog(
                ticker=ticker,
                entry_price=str(entry_price),
                shares=shares,
                **processed,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    # -- Alerts --------------------------------------------------------------

    async def save_alert(
        self,
        ticker: str,
        alert_type: str,
        severity: str,
        message: str | None = None,
    ) -> Alert:
        async with self._session_factory() as session:
            row = Alert(
                ticker=ticker,
                alert_type=alert_type,
                severity=severity,
                message=message,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    # -- Daily Scores --------------------------------------------------------

    async def save_daily_score(
        self,
        ticker: str,
        date: str,
        atm_score: Decimal | None = None,
        stability_score: Decimal | None = None,
        l2_score: Decimal | None = None,
        volume_score: Decimal | None = None,
        dilution_score: Decimal | None = None,
        ts_score: Decimal | None = None,
        ohi_score: Decimal | None = None,
    ) -> DailyScore:
        async with self._session_factory() as session:
            row = DailyScore(
                ticker=ticker,
                date=date,
                atm_score=str(atm_score) if atm_score is not None else None,
                stability_score=str(stability_score) if stability_score is not None else None,
                l2_score=str(l2_score) if l2_score is not None else None,
                volume_score=str(volume_score) if volume_score is not None else None,
                dilution_score=str(dilution_score) if dilution_score is not None else None,
                ts_score=str(ts_score) if ts_score is not None else None,
                ohi_score=str(ohi_score) if ohi_score is not None else None,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def upsert_daily_score(
        self,
        ticker: str,
        date: str,
        atm_score: Decimal | None = None,
        stability_score: Decimal | None = None,
        l2_score: Decimal | None = None,
        volume_score: Decimal | None = None,
        dilution_score: Decimal | None = None,
        ts_score: Decimal | None = None,
        ohi_score: Decimal | None = None,
    ) -> None:
        """Insert or update daily score by UNIQUE(ticker, date)."""
        values = {
            "ticker": ticker,
            "date": date,
            "atm_score": str(atm_score) if atm_score is not None else None,
            "stability_score": str(stability_score) if stability_score is not None else None,
            "l2_score": str(l2_score) if l2_score is not None else None,
            "volume_score": str(volume_score) if volume_score is not None else None,
            "dilution_score": str(dilution_score) if dilution_score is not None else None,
            "ts_score": str(ts_score) if ts_score is not None else None,
            "ohi_score": str(ohi_score) if ohi_score is not None else None,
        }
        update_cols = {k: v for k, v in values.items() if k not in ("ticker", "date")}
        async with self._session_factory() as session:
            stmt = (
                sqlite_insert(DailyScore)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["ticker", "date"],
                    set_=update_cols,
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def upsert_candidate(
        self,
        ticker: str,
        price_tier: str,
        atm_score: Decimal | None = None,
        status: str = "active",
    ) -> None:
        """Insert or update candidate by ticker. Updates score/status if exists."""
        values = {
            "ticker": ticker,
            "price_tier": price_tier,
            "first_seen": datetime.now(UTC),
            "atm_score": str(atm_score) if atm_score is not None else None,
            "status": status,
        }
        async with self._session_factory() as session:
            stmt = (
                sqlite_insert(Candidate)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["ticker"],
                    set_={
                        "atm_score": values["atm_score"],
                        "last_scored": datetime.now(UTC),
                        "status": status,
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()
