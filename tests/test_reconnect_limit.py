"""Tests for IBAdapter reconnect loop max attempts."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.event_bus import EventBus


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def adapter(bus):
    with patch("src.broker.ibkr.get_settings") as mock_settings:
        mock_settings.return_value.ibkr.host = "127.0.0.1"
        mock_settings.return_value.ibkr.port = 7497
        mock_settings.return_value.ibkr.client_id_data = 1
        mock_settings.return_value.ibkr.timeout = 10
        mock_settings.return_value.ibkr.max_l2_subscriptions = 2

        from src.broker.ibkr import IBAdapter
        a = IBAdapter(event_bus=bus)
    return a


@pytest.mark.asyncio
@patch("src.broker.ibkr.asyncio.sleep", new_callable=AsyncMock)
async def test_reconnect_exits_after_max_attempts(mock_sleep, adapter):
    """Engine should sys.exit(1) after _MAX_RECONNECT_ATTEMPTS failures."""
    adapter._ib.connectAsync = AsyncMock(side_effect=ConnectionError("refused"))
    adapter._ib.isConnected = MagicMock(return_value=False)

    with pytest.raises(SystemExit) as exc_info:
        await adapter._reconnect_loop()

    assert exc_info.value.code == 1
    assert mock_sleep.call_count == 50  # backoff sleep called each attempt


@pytest.mark.asyncio
@patch("src.broker.ibkr.asyncio.sleep", new_callable=AsyncMock)
async def test_reconnect_succeeds_before_max(mock_sleep, adapter):
    """Engine should reconnect if connection succeeds within limit."""
    call_count = 0

    async def connect_eventually(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("refused")
        adapter._ib.isConnected = MagicMock(return_value=True)

    adapter._ib.connectAsync = AsyncMock(side_effect=connect_eventually)
    adapter._ib.isConnected = MagicMock(return_value=False)
    adapter._resubscribe_all = AsyncMock()

    await adapter._reconnect_loop()

    assert call_count == 3
    adapter._resubscribe_all.assert_called_once()
    assert mock_sleep.call_count == 2  # slept on 2 failures before success
