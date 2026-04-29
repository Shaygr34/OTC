# Universe Scanner Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically discover ATM-eligible OTC stocks via IBKR's scanner API and insert them as candidates for the existing scoring pipeline.

**Architecture:** New `UniverseScanner` class runs on a 15-min asyncio timer, calls `reqScannerDataAsync()` for TRIPS and DUBS tiers, pre-filters by exchange (OTC only) and dedup, inserts to candidates table. Existing TickerWatcher → Screener → RuleEngine pipeline scores them.

**Tech Stack:** ib_async (`reqScannerDataAsync`, `ScannerSubscription`), SQLAlchemy, asyncio, structlog

**Spec:** `docs/superpowers/specs/2026-04-29-universe-scanner-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/scanner/universe.py` | Create | UniverseScanner — periodic OTC sweep, pre-filter, insert |
| `src/broker/adapter.py` | Modify | Add `request_scanner()` and `get_scanner_parameters()` abstract methods |
| `src/broker/ibkr.py` | Modify | Implement `request_scanner()` and `get_scanner_parameters()` |
| `src/broker/mock.py` | Modify | Implement `request_scanner()` and `get_scanner_parameters()` stubs |
| `src/database/repository.py` | Modify | Add `get_candidate_by_ticker()` |
| `config/settings.py` | Modify | Add `ScannerSettings` to `Settings` |
| `scripts/run_system.py` | Modify | Wire UniverseScanner into SystemRunner |
| `tests/test_universe_scanner.py` | Create | Tests for UniverseScanner |
| `tests/test_scanner_adapter.py` | Create | Tests for adapter scanner methods |
| `scripts/test_scanner_params.py` | Keep | Already created — live parameter discovery script |

---

## Task 1: Add scanner methods to BrokerAdapter ABC + MockAdapter

**Files:**
- Modify: `src/broker/adapter.py`
- Modify: `src/broker/mock.py`
- Create: `tests/test_scanner_adapter.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_scanner_adapter.py`:

```python
"""Tests for scanner methods on broker adapters."""

import pytest

from src.broker.mock import MockAdapter
from src.core.event_bus import EventBus


@pytest.fixture
def adapter():
    bus = EventBus()
    a = MockAdapter(bus)
    return a


@pytest.mark.asyncio
async def test_request_scanner_returns_list(adapter):
    await adapter.connect()
    results = await adapter.request_scanner(None)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_request_scanner_with_injected_data(adapter):
    await adapter.connect()
    adapter.set_scanner_results([
        {"symbol": "APTY", "exchange": "PINK"},
        {"symbol": "MWWC", "exchange": "PINK"},
    ])
    results = await adapter.request_scanner(None)
    assert len(results) == 2
    assert results[0]["symbol"] == "APTY"


@pytest.mark.asyncio
async def test_get_scanner_parameters(adapter):
    await adapter.connect()
    params = await adapter.get_scanner_parameters()
    assert isinstance(params, str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_scanner_adapter.py -v`
Expected: FAIL — methods don't exist

- [ ] **Step 3: Add abstract methods to BrokerAdapter**

In `src/broker/adapter.py`, add after `request_historical_bars`:

```python
    # ── Scanner ──────────────────────────────────────────────

    @abstractmethod
    async def request_scanner(self, subscription: object) -> list:
        """Run a scanner request and return results.

        ``subscription`` is a broker-specific scanner config object.
        Returns a list of results (broker-specific format).
        """

    @abstractmethod
    async def get_scanner_parameters(self) -> str:
        """Return available scanner parameters as a string (XML for IBKR)."""
```

- [ ] **Step 4: Implement in MockAdapter**

In `src/broker/mock.py`, add to `__init__`:

```python
self._scanner_results: list[dict] = []
```

Add methods:

```python
    # ── Scanner ──────────────────────────────────────────────

    async def request_scanner(self, subscription: object) -> list:
        self._ensure_connected()
        return list(self._scanner_results)

    async def get_scanner_parameters(self) -> str:
        self._ensure_connected()
        return "<xml>mock scanner parameters</xml>"

    def set_scanner_results(self, results: list[dict]) -> None:
        """Inject scanner results for testing."""
        self._scanner_results = results
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest tests/test_scanner_adapter.py -v`
Expected: 3 passed

- [ ] **Step 6: Run full suite**

Run: `.venv/bin/pytest tests/ -x -q`
Expected: All pass (364+)

- [ ] **Step 7: Commit**

```bash
git add src/broker/adapter.py src/broker/mock.py tests/test_scanner_adapter.py
git commit -m "feat: add request_scanner and get_scanner_parameters to BrokerAdapter"
```

---

## Task 2: Implement scanner methods in IBAdapter

**Files:**
- Modify: `src/broker/ibkr.py`

- [ ] **Step 1: Add imports**

At top of `src/broker/ibkr.py`, add `ScannerSubscription` to the ib_async import:

```python
from ib_async import IB, ScannerSubscription, Stock
```

- [ ] **Step 2: Implement request_scanner**

Add after `request_historical_bars` method:

```python
    # ── Scanner ──────────────────────────────────────────────

    async def request_scanner(self, subscription: object) -> list:
        """Run a one-shot scanner request via reqScannerDataAsync."""
        self._ensure_connected()
        results = await asyncio.wait_for(
            self._ib.reqScannerDataAsync(subscription),
            timeout=10.0,
        )
        logger.info(
            "scanner_results",
            count=len(results) if results else 0,
        )
        return list(results) if results else []

    async def get_scanner_parameters(self) -> str:
        """Return XML string of all available scanner parameters."""
        self._ensure_connected()
        return await self._ib.reqScannerParametersAsync()
```

- [ ] **Step 3: Run full suite**

Run: `.venv/bin/pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/broker/ibkr.py
git commit -m "feat: implement request_scanner in IBAdapter via reqScannerDataAsync"
```

---

## Task 3: Add ScannerSettings + repo.get_candidate_by_ticker

**Files:**
- Modify: `config/settings.py`
- Modify: `src/database/repository.py`

- [ ] **Step 1: Add ScannerSettings to settings.py**

After `LogSettings` class, add:

```python
class ScannerSettings(BaseSettings):
    model_config = {"env_prefix": "SCANNER_", "env_file": _ENV_FILE, "extra": "ignore"}

    enabled: bool = True
    interval_minutes: int = 15
    max_results_per_scan: int = 50
```

Add to `Settings` class:

```python
    scanner: ScannerSettings = Field(default_factory=ScannerSettings)
```

- [ ] **Step 2: Add get_candidate_by_ticker to Repository**

In `src/database/repository.py`, add after `reject_candidate`:

```python
    async def get_candidate_by_ticker(self, ticker: str) -> Candidate | None:
        """Return a candidate by ticker, or None if not found."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Candidate).where(Candidate.ticker == ticker)
            )
            return result.scalar_one_or_none()
```

- [ ] **Step 3: Run full suite**

Run: `.venv/bin/pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add config/settings.py src/database/repository.py
git commit -m "feat: add ScannerSettings and repo.get_candidate_by_ticker"
```

---

## Task 4: Build UniverseScanner

**Files:**
- Create: `src/scanner/universe.py`
- Create: `tests/test_universe_scanner.py`

- [ ] **Step 1: Write tests**

Create `tests/test_universe_scanner.py`:

```python
"""Tests for UniverseScanner — OTC universe discovery."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from config.settings import ScannerSettings
from src.core.event_bus import EventBus
from src.broker.mock import MockAdapter
from src.database.repository import Repository, get_engine, get_session_factory
from src.database.schema import create_all_tables
from src.scanner.universe import UniverseScanner


@dataclass
class MockContractDetails:
    contract: MagicMock

    def __post_init__(self):
        if self.contract is None:
            self.contract = MagicMock()


@dataclass
class MockScanData:
    rank: int
    contractDetails: MockContractDetails
    distance: str = ""
    benchmark: str = ""
    projection: str = ""
    legsStr: str = ""


def _make_scan_result(symbol: str, exchange: str = "PINK") -> MockScanData:
    contract = MagicMock()
    contract.symbol = symbol
    contract.exchange = "SMART"
    contract.primaryExchange = exchange
    details = MockContractDetails(contract=contract)
    details.validExchanges = f"SMART,{exchange}"
    return MockScanData(rank=0, contractDetails=details)


@pytest.fixture
async def scanner():
    bus = EventBus()
    adapter = MockAdapter(bus)
    await adapter.connect()
    engine = get_engine("sqlite+aiosqlite://")
    session_factory = get_session_factory(engine)
    await create_all_tables(engine)
    repo = Repository(session_factory)
    settings = ScannerSettings(enabled=True, interval_minutes=15, max_results_per_scan=50)
    s = UniverseScanner(adapter=adapter, repo=repo, settings=settings)
    yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_scan_once_inserts_new_candidates(scanner):
    """Scanner should insert new tickers as active candidates."""
    scanner._adapter.set_scanner_results([
        _make_scan_result("APTY", "PINK"),
        _make_scan_result("NEWT", "PINK"),
    ])
    count = await scanner.scan_once()
    assert count == 2

    candidate = await scanner._repo.get_candidate_by_ticker("APTY")
    assert candidate is not None
    assert candidate.status == "active"


@pytest.mark.asyncio
async def test_scan_once_skips_existing_candidates(scanner):
    """Scanner should not duplicate existing candidates."""
    # Insert one first
    await scanner._repo.upsert_candidate("APTY", "TRIPS", "active", "PINK")

    scanner._adapter.set_scanner_results([
        _make_scan_result("APTY", "PINK"),
        _make_scan_result("NEWT", "PINK"),
    ])
    count = await scanner.scan_once()
    assert count == 1  # Only NEWT inserted


@pytest.mark.asyncio
async def test_scan_once_filters_non_otc_exchanges(scanner):
    """Scanner should reject tickers not on PINK/GREY."""
    scanner._adapter.set_scanner_results([
        _make_scan_result("AAPL", "NASDAQ"),
        _make_scan_result("NEWT", "PINK"),
    ])
    count = await scanner.scan_once()
    assert count == 1  # Only NEWT


@pytest.mark.asyncio
async def test_scan_once_handles_empty_results(scanner):
    """Scanner should handle zero results gracefully."""
    scanner._adapter.set_scanner_results([])
    count = await scanner.scan_once()
    assert count == 0


@pytest.mark.asyncio
async def test_start_stop(scanner):
    """Scanner loop should start and stop cleanly."""
    await scanner.start()
    assert scanner._running
    await scanner.stop()
    assert not scanner._running
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_universe_scanner.py -v`
Expected: FAIL — `src.scanner.universe` doesn't exist

- [ ] **Step 3: Implement UniverseScanner**

Create `src/scanner/universe.py`:

```python
"""Automated OTC universe scanner via IBKR reqScannerDataAsync.

Periodically sweeps the OTC universe for ATM-eligible stocks and inserts
new discoveries into the candidates table for the scoring pipeline.
"""

import asyncio

import structlog
from ib_async import ScannerSubscription

from src.broker.adapter import BrokerAdapter
from src.database.repository import Repository

logger = structlog.get_logger(__name__)

_OTC_EXCHANGES = frozenset({"PINK", "GREY", "OTC", "VALUE", "PINKC"})

# Scanner configs per tier
_TIER_CONFIGS = [
    {
        "name": "TRIPS",
        "price_tier": "TRIPS",
        "subscription": ScannerSubscription(
            instrument="STK",
            locationCode="STK.US",
            scanCode="MOST_ACTIVE",
            abovePrice=0.0001,
            belowPrice=0.001,
            aboveVolume=1000,
            numberOfRows=50,
        ),
    },
    {
        "name": "DUBS",
        "price_tier": "DUBS",
        "subscription": ScannerSubscription(
            instrument="STK",
            locationCode="STK.US",
            scanCode="MOST_ACTIVE",
            abovePrice=0.001,
            belowPrice=0.01,
            aboveVolume=10000,
            numberOfRows=50,
        ),
    },
]


class UniverseScanner:
    """Periodic OTC universe sweep via IBKR scanner API."""

    def __init__(
        self,
        adapter: BrokerAdapter,
        repo: Repository,
        settings: object,
    ) -> None:
        self._adapter = adapter
        self._repo = repo
        self._settings = settings
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the periodic scan loop."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "universe_scanner_started",
            interval_minutes=self._settings.interval_minutes,
        )

    async def stop(self) -> None:
        """Cancel the scan loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("universe_scanner_stopped")

    async def _loop(self) -> None:
        """Run scan_once every interval_minutes."""
        while self._running:
            try:
                count = await self.scan_once()
                logger.info("universe_scan_complete", new_candidates=count)
            except Exception:
                logger.exception("universe_scan_error")
            await asyncio.sleep(self._settings.interval_minutes * 60)

    async def scan_once(self) -> int:
        """Run one sweep across all tier configs. Returns new candidates inserted."""
        total = 0
        for config in _TIER_CONFIGS:
            try:
                results = await self._adapter.request_scanner(config["subscription"])
                logger.info(
                    "universe_scan_tier",
                    tier=config["name"],
                    raw_results=len(results),
                )
            except Exception:
                logger.exception("universe_scan_tier_error", tier=config["name"])
                continue

            filtered = await self._filter_results(results)
            logger.info(
                "universe_scan_filtered",
                tier=config["name"],
                passed=len(filtered),
            )

            inserted = await self._insert_candidates(filtered, config["price_tier"])
            total += inserted

        return total

    async def _filter_results(self, results: list) -> list:
        """Remove duplicates and non-OTC tickers."""
        filtered = []
        for result in results:
            details = result.contractDetails if hasattr(result, "contractDetails") else result
            contract = details.contract if hasattr(details, "contract") else None

            if contract is None:
                continue

            symbol = getattr(contract, "symbol", None)
            if not symbol:
                continue

            # Check exchange — primaryExchange or validExchanges
            primary = getattr(contract, "primaryExchange", "")
            valid = getattr(details, "validExchanges", "")
            exchanges = {primary} | set(valid.split(",")) if valid else {primary}

            if not exchanges & _OTC_EXCHANGES:
                logger.debug(
                    "universe_scan_skip_exchange",
                    symbol=symbol,
                    exchanges=exchanges,
                )
                continue

            # Dedup against existing candidates
            existing = await self._repo.get_candidate_by_ticker(symbol)
            if existing is not None:
                continue

            filtered.append(result)

        return filtered

    async def _insert_candidates(self, results: list, price_tier: str) -> int:
        """Insert filtered results into candidates table."""
        count = 0
        for result in results:
            details = result.contractDetails if hasattr(result, "contractDetails") else result
            contract = details.contract if hasattr(details, "contract") else None
            symbol = getattr(contract, "symbol", "")
            primary = getattr(contract, "primaryExchange", "PINK")
            exchange = primary if primary in _OTC_EXCHANGES else "PINK"

            try:
                await self._repo.upsert_candidate(
                    ticker=symbol,
                    price_tier=price_tier,
                    status="active",
                    exchange=exchange,
                )
                count += 1
                logger.info(
                    "universe_scan_inserted",
                    symbol=symbol,
                    tier=price_tier,
                    exchange=exchange,
                )
            except Exception:
                logger.exception("universe_scan_insert_error", symbol=symbol)

        return count
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_universe_scanner.py -v`
Expected: 5 passed

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/scanner/universe.py tests/test_universe_scanner.py
git commit -m "feat: add UniverseScanner — automated OTC ticker discovery"
```

---

## Task 5: Wire UniverseScanner into SystemRunner

**Files:**
- Modify: `scripts/run_system.py`

- [ ] **Step 1: Add import**

In `scripts/run_system.py`, add:

```python
from src.scanner.universe import UniverseScanner
```

- [ ] **Step 2: Add to SystemRunner.__init__**

After the `TickerWatcher` creation block, add:

```python
        # ── Universe Scanner ──
        self.universe_scanner: UniverseScanner | None = None
        if self._settings.scanner.enabled:
            self.universe_scanner = UniverseScanner(
                adapter=self.adapter,
                repo=self._repo,
                settings=self._settings.scanner,
            )
```

- [ ] **Step 3: Start scanner in SystemRunner.start()**

After `self.ticker_watcher.start()`, add:

```python
        # Start universe scanner if enabled
        if self.universe_scanner is not None:
            await self.universe_scanner.start()
            logger.info(
                "universe_scanner_started",
                interval=self._settings.scanner.interval_minutes,
            )
```

- [ ] **Step 4: Stop scanner in SystemRunner.stop()**

Before `await self.ticker_watcher.stop()`, add:

```python
        if self.universe_scanner is not None:
            await self.universe_scanner.stop()
```

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add scripts/run_system.py
git commit -m "feat: wire UniverseScanner into SystemRunner"
```

---

## Task 6: Update CLAUDE.md + push + redeploy

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add Phase 15 to Build Progress**

After Phase 14, add:

```markdown
### Phase 15 — Universe Scanner (2026-04-29)

Automated OTC ticker discovery via IBKR `reqScannerDataAsync`.

**Code changes:**
- `src/scanner/universe.py` — UniverseScanner: periodic 15-min sweep, TRIPS + DUBS tier configs, exchange post-filter, dedup, auto-insert to candidates
- `src/broker/adapter.py` — added `request_scanner()` and `get_scanner_parameters()` abstract methods
- `src/broker/ibkr.py` — implemented via `reqScannerDataAsync` with 10s timeout
- `src/broker/mock.py` — injectable scanner results for testing
- `src/database/repository.py` — added `get_candidate_by_ticker()`
- `config/settings.py` — `ScannerSettings` (SCANNER_ENABLED, SCANNER_INTERVAL_MINUTES, SCANNER_MAX_RESULTS_PER_SCAN)

**Flow:** Scanner discovers → pre-filter (OTC exchange + dedup) → insert as active candidate → TickerWatcher subscribes → Screener evaluates → RuleEngine scores
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for Phase 15 — Universe Scanner"
```

- [ ] **Step 3: Push to main**

```bash
git push origin main
```

Railway auto-redeploys atm-engine from main. The scanner will start running on next deploy.

- [ ] **Step 4: Verify deployment**

```bash
railway service atm-engine && railway logs | tail -20
```

Look for: `universe_scanner_started interval_minutes=15`

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Scanner methods on adapter ABC + mock | adapter.py, mock.py, test |
| 2 | IBAdapter scanner implementation | ibkr.py |
| 3 | ScannerSettings + repo dedup query | settings.py, repository.py |
| 4 | UniverseScanner core module + tests | universe.py, test |
| 5 | Wire into SystemRunner | run_system.py |
| 6 | CLAUDE.md + push + deploy | CLAUDE.md |
