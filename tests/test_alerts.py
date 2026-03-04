"""Tests for the alert system (Phase 7).

Covers: dispatcher priority routing, Telegram channel (mocked),
event integration, min_priority filtering, history tracking.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.alerts.dispatcher import AlertDispatcher, Priority
from src.alerts.telegram import TelegramChannel
from src.core.event_bus import EventBus
from src.core.events import AlertEvent, DilutionAlertEvent

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def mock_telegram():
    """TelegramChannel with send() mocked to return True."""
    channel = TelegramChannel(bot_token="fake-token", chat_id="fake-chat")
    channel._enabled = True
    channel._bot = object()  # non-None to pass enabled check
    channel.send = AsyncMock(return_value=True)
    return channel


@pytest.fixture
def dispatcher(bus, mock_telegram):
    return AlertDispatcher(bus, telegram=mock_telegram)


@pytest.fixture
def dispatcher_no_telegram(bus):
    return AlertDispatcher(bus)


# ── Priority Mapping Tests ───────────────────────────────────────


class TestPriorityMapping:
    async def test_info_alert_is_low_priority(self, bus, dispatcher, mock_telegram):
        dispatcher.start()
        event = AlertEvent(
            ticker="ABCD",
            alert_type="VOLUME_ANOMALY",
            severity="INFO",
            message="Minor volume bump",
        )
        await bus.publish(event)
        assert len(dispatcher.history) == 1
        assert dispatcher.history[0].priority == Priority.LOW

    async def test_warning_alert_is_medium(self, bus, dispatcher):
        dispatcher.start()
        event = AlertEvent(
            ticker="ABCD",
            alert_type="VOLUME_ANOMALY",
            severity="WARNING",
            message="Volume spike z=3.2",
        )
        await bus.publish(event)
        assert dispatcher.history[0].priority == Priority.MEDIUM

    async def test_high_alert_is_high(self, bus, dispatcher):
        dispatcher.start()
        event = AlertEvent(
            ticker="ABCD",
            alert_type="VOLUME_ANOMALY",
            severity="HIGH",
            message="Extreme volume",
        )
        await bus.publish(event)
        assert dispatcher.history[0].priority == Priority.HIGH

    async def test_critical_alert_is_critical(self, bus, dispatcher):
        dispatcher.start()
        event = AlertEvent(
            ticker="ABCD",
            alert_type="BID_COLLAPSE",
            severity="CRITICAL",
            message="Bid collapsed",
        )
        await bus.publish(event)
        assert dispatcher.history[0].priority == Priority.CRITICAL


class TestDilutionPriority:
    async def test_dilution_warning_is_high(self, bus, dispatcher):
        dispatcher.start()
        event = DilutionAlertEvent(
            ticker="ABCD",
            dilution_score=4,
            severity="WARNING",
            signals=("Volume spike: z=3.5",),
            message="Dilution warning",
        )
        await bus.publish(event)
        assert dispatcher.history[0].priority == Priority.HIGH
        assert dispatcher.history[0].source == "dilution"

    async def test_dilution_high_alert_is_critical(self, bus, dispatcher):
        dispatcher.start()
        event = DilutionAlertEvent(
            ticker="ABCD",
            dilution_score=6,
            severity="HIGH_ALERT",
            signals=("Bad MM: MAXM", "Volume spike"),
            message="Dilution high alert",
        )
        await bus.publish(event)
        assert dispatcher.history[0].priority == Priority.CRITICAL

    async def test_dilution_critical_is_critical(self, bus, dispatcher):
        dispatcher.start()
        event = DilutionAlertEvent(
            ticker="ABCD",
            dilution_score=8,
            severity="CRITICAL",
            signals=("Bad MM: MAXM", "Volume spike", "Bid erosion"),
            message="Exit immediately",
        )
        await bus.publish(event)
        assert dispatcher.history[0].priority == Priority.CRITICAL


# ── Dispatch & Send Tests ─────────────────────────────────────────


class TestDispatching:
    async def test_sends_via_telegram(self, bus, dispatcher, mock_telegram):
        dispatcher.start()
        event = AlertEvent(
            ticker="ABCD",
            alert_type="VOLUME_ANOMALY",
            severity="WARNING",
            message="Volume spike",
        )
        await bus.publish(event)
        mock_telegram.send.assert_called_once()
        assert dispatcher.history[0].sent is True

    async def test_no_telegram_still_logs(self, bus, dispatcher_no_telegram):
        dispatcher_no_telegram.start()
        event = AlertEvent(
            ticker="ABCD",
            alert_type="VOLUME_ANOMALY",
            severity="WARNING",
            message="Volume spike",
        )
        await bus.publish(event)
        assert len(dispatcher_no_telegram.history) == 1
        assert dispatcher_no_telegram.history[0].sent is False

    async def test_message_format_alert(self, bus, dispatcher, mock_telegram):
        dispatcher.start()
        event = AlertEvent(
            ticker="WXYZ",
            alert_type="BID_COLLAPSE",
            severity="HIGH",
            message="Bid dropped 80%",
        )
        await bus.publish(event)
        sent_msg = mock_telegram.send.call_args[0][0]
        assert "WXYZ" in sent_msg
        assert "BID_COLLAPSE" in sent_msg
        assert "Bid dropped 80%" in sent_msg

    async def test_message_format_dilution(self, bus, dispatcher, mock_telegram):
        dispatcher.start()
        event = DilutionAlertEvent(
            ticker="XYZW",
            dilution_score=5,
            severity="HIGH_ALERT",
            signals=("Bad MM: MAXM", "Volume spike: z=4.2"),
            message="Dilution alert",
        )
        await bus.publish(event)
        sent_msg = mock_telegram.send.call_args[0][0]
        assert "XYZW" in sent_msg
        assert "5/10" in sent_msg
        assert "Bad MM: MAXM" in sent_msg


# ── Min Priority Filter Tests ────────────────────────────────────


class TestMinPriority:
    async def test_filters_below_threshold(self, bus, mock_telegram):
        dispatcher = AlertDispatcher(
            bus, telegram=mock_telegram, min_priority=Priority.HIGH
        )
        dispatcher.start()

        # LOW priority event should be filtered
        event = AlertEvent(
            ticker="ABCD",
            alert_type="VOLUME_ANOMALY",
            severity="INFO",
            message="Minor bump",
        )
        await bus.publish(event)
        mock_telegram.send.assert_not_called()
        assert dispatcher.history[0].sent is False

    async def test_passes_at_threshold(self, bus, mock_telegram):
        dispatcher = AlertDispatcher(
            bus, telegram=mock_telegram, min_priority=Priority.HIGH
        )
        dispatcher.start()

        event = AlertEvent(
            ticker="ABCD",
            alert_type="BID_COLLAPSE",
            severity="HIGH",
            message="Bid dropped",
        )
        await bus.publish(event)
        mock_telegram.send.assert_called_once()
        assert dispatcher.history[0].sent is True

    async def test_passes_above_threshold(self, bus, mock_telegram):
        dispatcher = AlertDispatcher(
            bus, telegram=mock_telegram, min_priority=Priority.MEDIUM
        )
        dispatcher.start()

        event = AlertEvent(
            ticker="ABCD",
            alert_type="BID_COLLAPSE",
            severity="CRITICAL",
            message="Critical alert",
        )
        await bus.publish(event)
        mock_telegram.send.assert_called_once()


# ── Telegram Channel Tests ───────────────────────────────────────


class TestTelegramChannel:
    def test_disabled_when_no_token(self):
        channel = TelegramChannel(bot_token="", chat_id="123")
        assert channel.enabled is False

    def test_disabled_when_no_chat_id(self):
        channel = TelegramChannel(bot_token="token", chat_id="")
        assert channel.enabled is False

    def test_enabled_with_both(self):
        channel = TelegramChannel(bot_token="token", chat_id="123")
        assert channel.enabled is True

    async def test_send_when_disabled(self):
        channel = TelegramChannel(bot_token="", chat_id="")
        result = await channel.send("test message")
        assert result is False

    async def test_send_when_bot_is_none(self):
        channel = TelegramChannel(bot_token="token", chat_id="123")
        # _bot is None (not initialized)
        result = await channel.send("test message")
        assert result is False

    async def test_initialize_without_telegram_lib(self):
        channel = TelegramChannel(bot_token="token", chat_id="123")
        with patch.dict("sys.modules", {"telegram": None}):
            await channel.initialize()
        # Should gracefully degrade
        assert channel._bot is None

    async def test_shutdown_when_no_bot(self):
        channel = TelegramChannel(bot_token="", chat_id="")
        # Should not raise
        await channel.shutdown()


# ── History Tests ────────────────────────────────────────────────


class TestHistory:
    async def test_multiple_alerts_tracked(self, bus, dispatcher):
        dispatcher.start()

        for i in range(3):
            event = AlertEvent(
                ticker=f"SYM{i}",
                alert_type="VOLUME_ANOMALY",
                severity="WARNING",
                message=f"Alert {i}",
            )
            await bus.publish(event)

        assert len(dispatcher.history) == 3
        tickers = [a.ticker for a in dispatcher.history]
        assert tickers == ["SYM0", "SYM1", "SYM2"]

    async def test_history_returns_copy(self, bus, dispatcher):
        dispatcher.start()
        event = AlertEvent(
            ticker="ABCD",
            alert_type="VOLUME_ANOMALY",
            severity="INFO",
            message="Test",
        )
        await bus.publish(event)
        h1 = dispatcher.history
        h2 = dispatcher.history
        assert h1 is not h2  # different list objects
        assert h1 == h2      # same content
