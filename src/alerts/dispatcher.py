"""Alert dispatcher — priority routing for AlertEvent and DilutionAlertEvent.

Subscribes to alert events on the EventBus, classifies priority,
and routes to configured channels (Telegram, future: Discord, etc.).
"""

from dataclasses import dataclass
from enum import IntEnum

import structlog

from src.alerts.telegram import TelegramChannel
from src.core.event_bus import EventBus
from src.core.events import AlertEvent, DilutionAlertEvent

logger = structlog.get_logger(__name__)


class Priority(IntEnum):
    """Alert priority levels (higher = more urgent)."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


# Severity → Priority mapping
_ALERT_PRIORITY: dict[str, Priority] = {
    "INFO": Priority.LOW,
    "WARNING": Priority.MEDIUM,
    "HIGH": Priority.HIGH,
    "CRITICAL": Priority.CRITICAL,
}

_DILUTION_PRIORITY: dict[str, Priority] = {
    "WARNING": Priority.HIGH,       # dilution warnings are always high
    "HIGH_ALERT": Priority.CRITICAL,
    "CRITICAL": Priority.CRITICAL,
}


@dataclass(frozen=True)
class DispatchedAlert:
    """Record of a dispatched alert."""

    ticker: str
    message: str
    priority: Priority
    source: str  # "alert" | "dilution"
    sent: bool


class AlertDispatcher:
    """Routes alerts to configured channels based on priority.

    Lifecycle:
        1. Construct with EventBus and optional TelegramChannel.
        2. Call ``start()`` to subscribe to AlertEvent + DilutionAlertEvent.
        3. Incoming events are classified, formatted, and routed.
    """

    def __init__(
        self,
        event_bus: EventBus,
        telegram: TelegramChannel | None = None,
        min_priority: Priority = Priority.LOW,
    ) -> None:
        self._event_bus = event_bus
        self._telegram = telegram
        self._min_priority = min_priority
        self._history: list[DispatchedAlert] = []

    @property
    def history(self) -> list[DispatchedAlert]:
        return list(self._history)

    def start(self) -> None:
        """Subscribe to alert events on the bus."""
        self._event_bus.subscribe(AlertEvent, self._on_alert)
        self._event_bus.subscribe(DilutionAlertEvent, self._on_dilution_alert)
        logger.info("alert_dispatcher_started")

    async def _on_alert(self, event: AlertEvent) -> None:
        """Handle a generic AlertEvent."""
        priority = _ALERT_PRIORITY.get(event.severity, Priority.MEDIUM)

        message = (
            f"[{event.severity}] {event.ticker}: {event.alert_type}\n"
            f"{event.message}"
        )

        await self._dispatch(event.ticker, message, priority, "alert")

    async def _on_dilution_alert(self, event: DilutionAlertEvent) -> None:
        """Handle a DilutionAlertEvent (always high priority)."""
        priority = _DILUTION_PRIORITY.get(event.severity, Priority.HIGH)

        signals = "\n".join(f"  - {s}" for s in event.signals)
        message = (
            f"DILUTION {event.severity} | {event.ticker}\n"
            f"Score: {event.dilution_score}/10\n"
            f"Signals:\n{signals}"
        )

        await self._dispatch(event.ticker, message, priority, "dilution")

    async def _dispatch(
        self,
        ticker: str,
        message: str,
        priority: Priority,
        source: str,
    ) -> None:
        """Route an alert to configured channels."""
        sent = False

        if priority < self._min_priority:
            logger.debug(
                "alert_below_threshold",
                ticker=ticker,
                priority=priority.name,
                min_priority=self._min_priority.name,
            )
            self._history.append(
                DispatchedAlert(
                    ticker=ticker,
                    message=message,
                    priority=priority,
                    source=source,
                    sent=False,
                )
            )
            return

        # Send via Telegram
        if self._telegram is not None:
            sent = await self._telegram.send(message, priority)

        logger.info(
            "alert_dispatched",
            ticker=ticker,
            priority=priority.name,
            source=source,
            sent=sent,
        )

        self._history.append(
            DispatchedAlert(
                ticker=ticker,
                message=message,
                priority=priority,
                source=source,
                sent=sent,
            )
        )
