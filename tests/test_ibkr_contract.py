"""Tests for IBAdapter contract qualification and subscription guards.

Uses unittest.mock to simulate ib_async without a running TWS instance.
Covers: SMART-first fallback, None contract rejection, conId=0 rejection,
exchange fallback chain, and subscription guard (_ensure_valid_contract).
"""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.event_bus import EventBus


@dataclass
class FakeContract:
    """Minimal stand-in for ib_async.Stock after qualification."""

    symbol: str = "TEST"
    exchange: str = "SMART"
    currency: str = "USD"
    conId: int = 0
    secType: str = "STK"


def _make_ib_mock(qualify_side_effect=None):
    """Create a mock IB instance with common defaults."""
    ib = MagicMock()
    ib.isConnected.return_value = True
    ib.qualifyContractsAsync = AsyncMock(side_effect=qualify_side_effect)
    ib.connectAsync = AsyncMock()
    ib.reqMktData = MagicMock()
    ib.reqMktDepth = MagicMock()
    ib.reqTickByTickData = MagicMock()
    # Event attributes need += / -= support
    ib.pendingTickersEvent = MagicMock()
    ib.disconnectedEvent = MagicMock()
    ib.errorEvent = MagicMock()
    return ib


@pytest.fixture
def bus():
    b = EventBus()
    yield b
    b.reset()


@pytest.fixture
def adapter(bus):
    """Create an IBAdapter with a mocked IB connection."""
    with patch("src.broker.ibkr.IB") as MockIB, \
         patch("src.broker.ibkr.get_settings") as mock_settings:
        mock_settings.return_value.ibkr.host = "127.0.0.1"
        mock_settings.return_value.ibkr.port = 7497
        mock_settings.return_value.ibkr.client_id_data = 1
        mock_settings.return_value.ibkr.timeout = 10

        from src.broker.ibkr import IBAdapter
        a = IBAdapter(event_bus=bus)
        # Replace the IB instance with our mock
        a._ib = _make_ib_mock()
        return a


# ── Contract qualification: SMART-first fallback ─────────────────


class TestContractQualificationFallback:
    """Verify the SMART-first exchange resolution chain."""

    async def test_smart_succeeds_first(self, adapter):
        """When SMART qualifies, no other exchange is tried."""
        good = FakeContract(symbol="VNTH", exchange="SMART", conId=12345)

        call_count = 0

        async def qualify_once(contract):
            nonlocal call_count
            call_count += 1
            contract.conId = 12345
            contract.exchange = "SMART"
            return [good]

        adapter._ib.qualifyContractsAsync = AsyncMock(side_effect=qualify_once)

        result = await adapter.create_otc_contract("VNTH", "PINK")
        assert result.conId == 12345
        assert call_count == 1  # Only SMART was tried

    async def test_smart_fails_pink_succeeds(self, adapter):
        """If SMART fails (conId=0), PINK is tried next."""
        bad = FakeContract(symbol="VNTH", exchange="SMART", conId=0)
        good = FakeContract(symbol="VNTH", exchange="PINK", conId=99999)

        attempts = []

        async def qualify_fallback(contract):
            attempts.append(contract.exchange)
            if contract.exchange == "SMART":
                return [bad]
            good_copy = FakeContract(
                symbol="VNTH", exchange=contract.exchange, conId=99999,
            )
            return [good_copy]

        adapter._ib.qualifyContractsAsync = AsyncMock(
            side_effect=qualify_fallback
        )

        result = await adapter.create_otc_contract("VNTH", "PINK")
        assert result.conId == 99999
        assert attempts[0] == "SMART"
        assert attempts[1] == "PINK"

    async def test_all_exchanges_fail_raises_valueerror(self, adapter):
        """If every exchange fails, ValueError is raised with details."""
        bad = FakeContract(conId=0)

        async def always_fail(contract):
            return [bad]

        adapter._ib.qualifyContractsAsync = AsyncMock(side_effect=always_fail)

        with pytest.raises(ValueError, match="Could not qualify contract"):
            await adapter.create_otc_contract("FAKE", "PINK")

    async def test_exchange_hint_grey_tried_second(self, adapter):
        """Exchange hint 'GREY' is tried right after SMART."""
        attempts = []

        async def track_and_fail(contract):
            attempts.append(contract.exchange)
            return [FakeContract(conId=0)]

        adapter._ib.qualifyContractsAsync = AsyncMock(
            side_effect=track_and_fail
        )

        with pytest.raises(ValueError):
            await adapter.create_otc_contract("TEST", "GREY")

        assert attempts[0] == "SMART"
        assert attempts[1] == "GREY"
        # No duplicates
        assert len(attempts) == len(set(attempts))

    async def test_cached_contract_returned_immediately(self, adapter):
        """Second call for same symbol returns cached contract."""
        good = FakeContract(symbol="ABCD", conId=555)

        async def qualify_ok(contract):
            return [good]

        adapter._ib.qualifyContractsAsync = AsyncMock(side_effect=qualify_ok)

        c1 = await adapter.create_otc_contract("ABCD", "PINK")
        c2 = await adapter.create_otc_contract("ABCD", "PINK")

        assert c1 is c2
        # qualifyContractsAsync only called once
        assert adapter._ib.qualifyContractsAsync.await_count == 1


# ── None contract handling ───────────────────────────────────────


class TestNoneContractRejection:
    """Verify that None and conId=0 contracts are never used."""

    async def test_qualify_returns_none_in_list(self, adapter):
        """qualifyContractsAsync returning [None] is handled gracefully."""
        async def return_none_list(contract):
            return [None]

        adapter._ib.qualifyContractsAsync = AsyncMock(
            side_effect=return_none_list
        )

        with pytest.raises(ValueError, match="Could not qualify"):
            await adapter.create_otc_contract("HADV", "PINK")

    async def test_qualify_returns_empty_list(self, adapter):
        """qualifyContractsAsync returning [] is handled gracefully."""
        async def return_empty(contract):
            return []

        adapter._ib.qualifyContractsAsync = AsyncMock(
            side_effect=return_empty
        )

        with pytest.raises(ValueError, match="Could not qualify"):
            await adapter.create_otc_contract("HADV", "PINK")

    async def test_qualify_returns_conid_zero(self, adapter):
        """Contract with conId=0 is rejected (unqualified)."""
        async def return_unqualified(contract):
            return [FakeContract(conId=0)]

        adapter._ib.qualifyContractsAsync = AsyncMock(
            side_effect=return_unqualified
        )

        with pytest.raises(ValueError, match="Could not qualify"):
            await adapter.create_otc_contract("HADV", "PINK")

    async def test_qualify_raises_exception_tries_next(self, adapter):
        """If qualifyContractsAsync raises, the next exchange is tried."""
        attempts = []

        async def fail_then_succeed(contract):
            attempts.append(contract.exchange)
            if contract.exchange == "SMART":
                raise RuntimeError("Network error")
            return [FakeContract(symbol="TEST", exchange="PINK", conId=42)]

        adapter._ib.qualifyContractsAsync = AsyncMock(
            side_effect=fail_then_succeed
        )

        result = await adapter.create_otc_contract("TEST", "PINK")
        assert result.conId == 42
        assert "SMART" in attempts


# ── Subscription guards ──────────────────────────────────────────


class TestSubscriptionGuards:
    """Verify _ensure_valid_contract prevents None from reaching IBKR API."""

    async def test_ensure_valid_contract_rejects_none(self, adapter):
        from src.broker.ibkr import IBAdapter
        with pytest.raises(ValueError, match="None"):
            IBAdapter._ensure_valid_contract(None, "TEST")

    async def test_ensure_valid_contract_rejects_conid_zero(self, adapter):
        from src.broker.ibkr import IBAdapter
        fake = FakeContract(conId=0)
        with pytest.raises(ValueError, match="unqualified"):
            IBAdapter._ensure_valid_contract(fake, "TEST")

    async def test_ensure_valid_contract_accepts_good(self, adapter):
        from src.broker.ibkr import IBAdapter
        fake = FakeContract(conId=12345)
        # Should not raise
        IBAdapter._ensure_valid_contract(fake, "TEST")

    async def test_subscribe_market_data_calls_qualify(self, adapter):
        """subscribe_market_data calls create_otc_contract before reqMktData."""
        good = FakeContract(conId=100)

        async def qualify_ok(contract):
            return [good]

        adapter._ib.qualifyContractsAsync = AsyncMock(side_effect=qualify_ok)

        await adapter.subscribe_market_data("VNTH", "PINK")

        adapter._ib.reqMktData.assert_called_once()
        assert "market_data" in adapter._subscriptions.get("VNTH", set())

    async def test_subscribe_l2_calls_qualify(self, adapter):
        """subscribe_l2_depth calls create_otc_contract before reqMktDepth."""
        good = FakeContract(conId=100)

        async def qualify_ok(contract):
            return [good]

        adapter._ib.qualifyContractsAsync = AsyncMock(side_effect=qualify_ok)

        await adapter.subscribe_l2_depth("VNTH", "PINK")

        adapter._ib.reqMktDepth.assert_called_once()
        assert "l2_depth" in adapter._subscriptions.get("VNTH", set())

    async def test_subscribe_tbt_calls_qualify(self, adapter):
        """subscribe_tick_by_tick calls create_otc_contract first."""
        good = FakeContract(conId=100)

        async def qualify_ok(contract):
            return [good]

        adapter._ib.qualifyContractsAsync = AsyncMock(side_effect=qualify_ok)

        await adapter.subscribe_tick_by_tick("VNTH", "PINK")

        adapter._ib.reqTickByTickData.assert_called_once()
        assert "tick_by_tick" in adapter._subscriptions.get("VNTH", set())


# ── Exchange fallback order ──────────────────────────────────────


class TestExchangeFallbackOrder:
    """Verify the full exchange fallback chain order."""

    async def test_full_fallback_order_default_pink(self, adapter):
        """Default hint=PINK: SMART, PINK, GREY, OTC, VALUE, PINKC."""
        attempts = []

        async def track(contract):
            attempts.append(contract.exchange)
            return [FakeContract(conId=0)]

        adapter._ib.qualifyContractsAsync = AsyncMock(side_effect=track)

        with pytest.raises(ValueError):
            await adapter.create_otc_contract("X", "PINK")

        assert attempts == ["SMART", "PINK", "GREY", "OTC", "VALUE", "PINKC"]

    async def test_full_fallback_order_custom_hint(self, adapter):
        """Custom hint=VALUE: SMART, VALUE, then remaining."""
        attempts = []

        async def track(contract):
            attempts.append(contract.exchange)
            return [FakeContract(conId=0)]

        adapter._ib.qualifyContractsAsync = AsyncMock(side_effect=track)

        with pytest.raises(ValueError):
            await adapter.create_otc_contract("X", "VALUE")

        assert attempts[0] == "SMART"
        assert attempts[1] == "VALUE"
        # No duplicates
        assert len(attempts) == len(set(attempts))
