"""Telegram channel — sends alerts via python-telegram-bot v21+.

Designed as an optional dependency: when bot_token is empty or
sending fails, alerts are logged but not sent. The system never
crashes due to Telegram issues.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class TelegramChannel:
    """Sends messages to a Telegram chat.

    Uses python-telegram-bot v21+ async API. Gracefully degrades
    when the bot is not configured or sending fails.
    """

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._bot: object | None = None
        self._enabled = bool(bot_token and chat_id)

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def initialize(self) -> None:
        """Initialize the Telegram bot. No-op if not configured."""
        if not self._enabled:
            logger.info("telegram_disabled", reason="missing bot_token or chat_id")
            return

        try:
            from telegram import Bot

            self._bot = Bot(token=self._bot_token)
            logger.info("telegram_initialized", chat_id=self._chat_id)
        except ImportError:
            logger.warning(
                "telegram_import_failed",
                reason="python-telegram-bot not installed",
            )
            self._enabled = False
        except Exception as exc:
            logger.error("telegram_init_error", error=str(exc))
            self._enabled = False

    async def send(self, message: str, priority: int = 1) -> bool:
        """Send a message to the configured chat.

        Returns True if sent successfully, False otherwise.
        Never raises — all errors are logged.
        """
        if not self._enabled or self._bot is None:
            logger.debug("telegram_send_skipped", reason="not enabled")
            return False

        try:
            # Priority prefix for urgent messages
            if priority >= 4:
                text = f"🚨 CRITICAL\n\n{message}"
            elif priority >= 3:
                text = f"⚠️ HIGH\n\n{message}"
            else:
                text = message

            await self._bot.send_message(  # type: ignore[union-attr]
                chat_id=self._chat_id,
                text=text,
                parse_mode=None,
            )
            logger.info("telegram_sent", chat_id=self._chat_id, priority=priority)
            return True

        except Exception as exc:
            logger.error("telegram_send_error", error=str(exc))
            return False

    async def shutdown(self) -> None:
        """Clean up the bot connection."""
        if self._bot is not None:
            try:
                await self._bot.shutdown()  # type: ignore[union-attr]
            except Exception as exc:
                logger.error("telegram_shutdown_error", error=str(exc))
            self._bot = None
