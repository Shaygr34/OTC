"""PersistenceSubscriber — wires pipeline events to database writes.

Subscribes to all event types that should be persisted and routes them
to the appropriate Repository methods. Runs as a passive listener on
the EventBus — zero impact on pipeline logic.
"""

from datetime import UTC, datetime

import structlog

from src.core.event_bus import EventBus
from src.core.events import (
    AlertEvent,
    AnalysisCompleteEvent,
    DilutionAlertEvent,
    L2UpdateEvent,
    ScannerHitEvent,
    TradeEvent,
)
from src.database.repository import Repository

logger = structlog.get_logger(__name__)


class PersistenceSubscriber:
    """Subscribes to pipeline events and persists them to SQLite."""

    def __init__(self, repo: Repository, event_bus: EventBus) -> None:
        self._repo = repo
        self._event_bus = event_bus
        self._seen_candidates: set[str] = set()

    def start(self) -> None:
        """Register all event subscriptions."""
        self._event_bus.subscribe(L2UpdateEvent, self._on_l2_update)
        self._event_bus.subscribe(TradeEvent, self._on_trade)
        self._event_bus.subscribe(AlertEvent, self._on_alert)
        self._event_bus.subscribe(DilutionAlertEvent, self._on_dilution_alert)
        self._event_bus.subscribe(AnalysisCompleteEvent, self._on_analysis_complete)
        self._event_bus.subscribe(ScannerHitEvent, self._on_scanner_hit)
        logger.info("persistence_started", subscriptions=6)

    async def _on_l2_update(self, event: L2UpdateEvent) -> None:
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
        await self._repo.save_l2_snapshot(
            ticker=event.ticker,
            timestamp=event.timestamp,
            bid_levels=bid_levels,
            ask_levels=ask_levels,
            total_bid_shares=total_bid,
            total_ask_shares=total_ask,
        )

    async def _on_trade(self, event: TradeEvent) -> None:
        await self._repo.save_trade(
            ticker=event.ticker,
            timestamp=event.timestamp,
            price=event.price,
            size=event.size,
            side=event.side,
            mm_id=event.mm_id,
        )

    async def _on_alert(self, event: AlertEvent) -> None:
        await self._repo.save_alert(
            ticker=event.ticker,
            alert_type=event.alert_type,
            severity=event.severity,
            message=event.message,
        )

    async def _on_dilution_alert(self, event: DilutionAlertEvent) -> None:
        await self._repo.save_alert(
            ticker=event.ticker,
            alert_type="DILUTION",
            severity=event.severity,
            message=event.message,
        )

    async def _on_analysis_complete(self, event: AnalysisCompleteEvent) -> None:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        await self._repo.upsert_daily_score(
            ticker=event.ticker,
            date=today,
            atm_score=event.atm_score,
            stability_score=event.stability_score,
            l2_score=event.l2_score,
            volume_score=event.volume_score,
            dilution_score=event.dilution_score,
            ts_score=event.ts_score,
            components_scored=event.components_scored,
            score_detail=event.score_detail,
        )

    async def _on_scanner_hit(self, event: ScannerHitEvent) -> None:
        if event.ticker in self._seen_candidates:
            return
        self._seen_candidates.add(event.ticker)
        await self._repo.upsert_candidate(
            ticker=event.ticker,
            price_tier=event.price_tier,
        )
        logger.info("candidate_persisted", ticker=event.ticker, tier=event.price_tier)
