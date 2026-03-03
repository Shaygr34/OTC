"""Lightweight async event bus using defaultdict(list).

Error isolation: one handler failure does not prevent other handlers from running.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._handlers: defaultdict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable) -> None:
        """Register an async handler for an event type."""
        self._handlers[event_type].append(handler)

    async def publish(self, event: Any) -> None:
        """Publish an event to all registered handlers.

        Handlers are called concurrently. Exceptions are logged but do not
        propagate — one failing handler never blocks the others.
        """
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return

        results = await asyncio.gather(
            *(h(event) for h in handlers),
            return_exceptions=True,
        )

        for handler, result in zip(handlers, results, strict=True):
            if isinstance(result, BaseException):
                try:
                    logger.error(
                        "event_handler_failed",
                        handler=handler.__qualname__,
                        event_type=event_type.__name__,
                        error=str(result),
                    )
                except Exception:
                    # Fallback if structlog is not configured
                    logging.getLogger(__name__).error(
                        "Event handler %s failed: %s", handler.__qualname__, result
                    )

    def reset(self) -> None:
        """Remove all subscriptions. For testing only."""
        self._handlers.clear()
