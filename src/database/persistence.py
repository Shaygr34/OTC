"""EventBus subscriber that persists events to the database.

Subscribes to L2UpdateEvent, TradeEvent, AlertEvent, DilutionAlertEvent,
and AnalysisCompleteEvent — writes each to SQLite via the Repository.
"""

import structlog

from src.core.event_bus import EventBus
from src.core.events import (
    AlertEvent,
    AnalysisCompleteEvent,
    DilutionAlertEvent,
    L2UpdateEvent,
    TradeEvent,
)
from src.database.repository import Repository

logger = structlog.get_logger(__name__)


class DatabasePersistence:
    """Subscribes to pipeline events and persists them to the database.

    Lifecycle:
        1. Construct with EventBus and Repository.
        2. Call ``start()`` to subscribe to events.
        3. Each event is written asynchronously — failures are logged, never crash.
    """

    def __init__(self, event_bus: EventBus, repository: Repository) -> None:
        self._event_bus = event_bus
        self._repo = repository

    def start(self) -> None:
        """Subscribe to all persistable events."""
        self._event_bus.subscribe(L2UpdateEvent, self._on_l2_update)
        self._event_bus.subscribe(TradeEvent, self._on_trade)
        self._event_bus.subscribe(AlertEvent, self._on_alert)
        self._event_bus.subscribe(DilutionAlertEvent, self._on_dilution_alert)
        self._event_bus.subscribe(AnalysisCompleteEvent, self._on_analysis_complete)
        logger.info("database_persistence_started")

    async def _on_l2_update(self, event: L2UpdateEvent) -> None:
        try:
            bid_levels = [
                {"price": str(p), "size": s, "mm_id": mm}
                for p, s, mm in event.bid_levels
            ]
            ask_levels = [
                {"price": str(p), "size": s, "mm_id": mm}
                for p, s, mm in event.ask_levels
            ]
            total_bid = sum(s for _, s, _ in event.bid_levels)
            total_ask = sum(s for _, s, _ in event.ask_levels)
            from decimal import Decimal

            ratio = (
                Decimal(str(total_bid)) / Decimal(str(total_ask))
                if total_ask > 0
                else None
            )
            await self._repo.save_l2_snapshot(
                ticker=event.ticker,
                timestamp=event.timestamp,
                bid_levels=bid_levels,
                ask_levels=ask_levels,
                imbalance_ratio=ratio,
                total_bid_shares=total_bid,
                total_ask_shares=total_ask,
            )
            logger.debug("l2_snapshot_persisted", ticker=event.ticker)
        except Exception:
            logger.exception("l2_snapshot_persist_failed", ticker=event.ticker)

    async def _on_trade(self, event: TradeEvent) -> None:
        try:
            await self._repo.save_trade(
                ticker=event.ticker,
                timestamp=event.timestamp,
                price=event.price,
                size=event.size,
                side=event.side,
                mm_id=event.mm_id or None,
            )
            logger.debug("trade_persisted", ticker=event.ticker)
        except Exception:
            logger.exception("trade_persist_failed", ticker=event.ticker)

    async def _on_alert(self, event: AlertEvent) -> None:
        try:
            await self._repo.save_alert(
                ticker=event.ticker,
                alert_type=event.alert_type,
                severity=event.severity,
                message=event.message,
            )
            logger.debug("alert_persisted", ticker=event.ticker)
        except Exception:
            logger.exception("alert_persist_failed", ticker=event.ticker)

    async def _on_dilution_alert(self, event: DilutionAlertEvent) -> None:
        try:
            signals_str = "; ".join(event.signals)
            await self._repo.save_alert(
                ticker=event.ticker,
                alert_type="DILUTION",
                severity=event.severity,
                message=f"Score: {event.dilution_score}/10 | {signals_str}",
            )
            logger.debug("dilution_alert_persisted", ticker=event.ticker)
        except Exception:
            logger.exception("dilution_alert_persist_failed", ticker=event.ticker)

    async def _on_analysis_complete(self, event: AnalysisCompleteEvent) -> None:
        try:
            date_str = event.timestamp.strftime("%Y-%m-%d")
            await self._repo.save_daily_score(
                ticker=event.ticker,
                date=date_str,
                atm_score=event.atm_score,
                stability_score=event.stability_score,
                l2_score=event.l2_score,
                volume_score=event.volume_score,
                dilution_score=event.dilution_score,
                ts_score=event.ts_score,
            )
            logger.debug("daily_score_persisted", ticker=event.ticker)
        except Exception:
            logger.exception("daily_score_persist_failed", ticker=event.ticker)
