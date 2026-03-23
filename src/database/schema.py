"""SQLAlchemy 2.0 declarative models matching the spec's SQL schema.

Prices are stored as TEXT (String) to preserve Decimal precision.
JSON columns store L2 level arrays.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    price_tier: Mapped[str] = mapped_column(String, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_scored: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    atm_score: Mapped[str | None] = mapped_column(String, nullable=True)  # Decimal as text
    status: Mapped[str] = mapped_column(String, default="active")
    exchange: Mapped[str] = mapped_column(String, default="PINK")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class L2SnapshotRow(Base):
    __tablename__ = "l2_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bid_levels: Mapped[dict] = mapped_column(JSON, nullable=False)
    ask_levels: Mapped[dict] = mapped_column(JSON, nullable=False)
    imbalance_ratio: Mapped[str | None] = mapped_column(String, nullable=True)
    total_bid_shares: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_ask_shares: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TradeRow(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[str] = mapped_column(String, nullable=False)  # Decimal as text
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str | None] = mapped_column(String, nullable=True)
    mm_id: Mapped[str | None] = mapped_column(String, nullable=True)


class TradeLog(Base):
    __tablename__ = "trade_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    timestamp_entry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timestamp_exit: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_price: Mapped[str] = mapped_column(String, nullable=False)
    exit_price: Mapped[str | None] = mapped_column(String, nullable=True)
    shares: Mapped[int] = mapped_column(Integer, nullable=False)
    position_pct: Mapped[str | None] = mapped_column(String, nullable=True)
    portfolio_value_at_entry: Mapped[str | None] = mapped_column(String, nullable=True)
    l2_ratio_at_entry: Mapped[str | None] = mapped_column(String, nullable=True)
    atm_score_at_entry: Mapped[str | None] = mapped_column(String, nullable=True)
    bad_mm_present: Mapped[bool] = mapped_column(Boolean, default=False)
    avg_volume_30d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tracking_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    pnl_usd: Mapped[str | None] = mapped_column(String, nullable=True)
    pnl_pct: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    alert_type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


class DailyScore(Base):
    __tablename__ = "daily_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[str] = mapped_column(String, nullable=False)
    atm_score: Mapped[str | None] = mapped_column(String, nullable=True)
    stability_score: Mapped[str | None] = mapped_column(String, nullable=True)
    l2_score: Mapped[str | None] = mapped_column(String, nullable=True)
    volume_score: Mapped[str | None] = mapped_column(String, nullable=True)
    dilution_score: Mapped[str | None] = mapped_column(String, nullable=True)
    ts_score: Mapped[str | None] = mapped_column(String, nullable=True)
    ohi_score: Mapped[str | None] = mapped_column(String, nullable=True)
    components_scored: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (UniqueConstraint("ticker", "date"),)


async def create_all_tables(engine: AsyncEngine) -> None:
    """Create all tables. Idempotent — safe to call on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Migrate: add exchange column to candidates if missing (for existing DBs)
    async with engine.begin() as conn:
        try:
            await conn.execute(
                text("ALTER TABLE candidates ADD COLUMN exchange TEXT DEFAULT 'PINK'")
            )
        except Exception:
            pass  # Column already exists
