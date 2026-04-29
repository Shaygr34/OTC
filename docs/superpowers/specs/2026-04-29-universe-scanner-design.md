# OTC Universe Scanner — Automated Ticker Discovery

**Date:** 2026-04-29
**Status:** Design
**Goal:** Automatically discover ATM-eligible OTC stocks via IBKR's scanner API and feed them into the existing scoring pipeline.

---

## Architecture

```
UniverseScanner (asyncio timer, every 15 min)
    │
    ├── reqScannerSubscription(TRIPS config)  → up to 50 tickers
    ├── reqScannerSubscription(DUBS config)   → up to 50 tickers
    │
    ├── Pre-filter: dedup vs candidates table
    ├── Pre-filter: spread > 50% → reject
    │
    └── Insert to candidates table (status='active', price_tier, exchange)
            │
            ▼
    TickerWatcher (existing 5s poll) picks up new candidates
            │
            ▼
    Screener → L2 → Volume → T&S → RuleEngine → Score
```

### What's new
- `src/scanner/universe.py` — `UniverseScanner` class
- `config/settings.py` — `ScannerSettings` added to `Settings`
- `scripts/run_system.py` — wire UniverseScanner into SystemRunner

### What's unchanged
- TickerWatcher, Screener, all analyzers, RuleEngine, persistence, alerts
- Database schema (uses existing candidates table)
- Dashboard

---

## UniverseScanner Class

```python
class UniverseScanner:
    """Periodic OTC universe sweep via IBKR reqScannerSubscription."""

    def __init__(
        self,
        adapter: BrokerAdapter,
        repo: Repository,
        settings: ScannerSettings,
    ) -> None:
        ...

    async def start(self) -> None:
        """Start the periodic scan loop."""

    async def stop(self) -> None:
        """Cancel the scan loop."""

    async def scan_once(self) -> int:
        """Run one sweep across all tier configs. Returns count of new candidates inserted."""

    async def _scan_tier(self, config: ScannerSubscription) -> list[ScanData]:
        """Execute a single scanner subscription request."""

    async def _pre_filter(self, results: list[ScanData]) -> list[ScanData]:
        """Remove duplicates and spread-rejected tickers."""

    async def _insert_candidates(self, results: list[ScanData], tier: str) -> int:
        """Insert filtered results into candidates table."""
```

---

## Scanner Configurations

### TRIPS Scan ($0.0001–$0.001)

```python
ScannerSubscription(
    instrument="STK",
    locationCode="STK.US.MINOR",  # OTC/Pink stocks
    scanCode="TOP_PERC_GAIN",     # Active stocks — will test alternatives
    abovePrice=0.0001,
    belowPrice=0.001,
    aboveVolume=10000,            # Minimum daily volume
    numberOfRows=50,
)
```

### DUBS Scan ($0.001–$0.01)

```python
ScannerSubscription(
    instrument="STK",
    locationCode="STK.US.MINOR",
    scanCode="TOP_PERC_GAIN",
    abovePrice=0.001,
    belowPrice=0.01,
    aboveVolume=10000,
    numberOfRows=50,
)
```

**Note on `locationCode`:** IBKR uses `STK.US.MINOR` for OTC/Pink Sheet stocks. If this doesn't return results, fallback to `STK.US` with post-filter by exchange. The exact location code will be validated during implementation by calling `reqScannerParameters()` which returns the full XML of available codes.

**Note on `scanCode`:** `TOP_PERC_GAIN` is a starting point. Other candidates: `MOST_ACTIVE`, `TOP_TRADE_COUNT`, `HOT_BY_VOLUME`. We'll test which returns the best OTC candidates. Multiple scan codes can be run per tier if needed.

---

## Pre-Filters

Before inserting a discovered ticker into the candidates table:

1. **Dedup check** — Skip if ticker already exists in candidates table (any status). Uses `repo.get_candidate_by_ticker()`.

2. **Spread check** — For DUBS tier, compute spread from the scanner result's contract details. If bid/ask spread > 50%, skip. TRIPS tier skips this check (spreads are always wide at sub-penny levels).

3. **Exchange validation** — Only accept tickers on PINK or GREY exchanges. Filter by `contractDetails.contract.primaryExchange`.

---

## Settings

```python
class ScannerSettings(BaseSettings):
    model_config = {"env_prefix": "SCANNER_", "env_file": _ENV_FILE, "extra": "ignore"}

    enabled: bool = True
    interval_minutes: int = 15
    max_results_per_scan: int = 50
```

Added to `Settings` as `scanner: ScannerSettings`.

Environment variables:
- `SCANNER_ENABLED=true` (default)
- `SCANNER_INTERVAL_MINUTES=15` (default)
- `SCANNER_MAX_RESULTS_PER_SCAN=50` (default)

---

## SystemRunner Integration

In `scripts/run_system.py`:

```python
# After all existing modules start...
if self._settings.scanner.enabled:
    self.universe_scanner = UniverseScanner(
        adapter=self.adapter,
        repo=self._repo,
        settings=self._settings.scanner,
    )
    await self.universe_scanner.start()
    logger.info("universe_scanner_started", interval=self._settings.scanner.interval_minutes)
```

In `stop()`:
```python
if hasattr(self, 'universe_scanner'):
    await self.universe_scanner.stop()
```

---

## IBAdapter Changes

Add one new method to `src/broker/ibkr.py`:

```python
async def request_scanner(self, subscription: ScannerSubscription) -> list:
    """Run a scanner subscription and return results."""
    self._ensure_connected()
    results = self._ib.reqScannerSubscription(subscription)
    # Wait for results (ib_async returns ScanDataList)
    await asyncio.sleep(2)  # Scanner needs time to return
    self._ib.cancelScannerSubscription(results)
    return list(results)
```

Also add a one-time discovery method:

```python
async def get_scanner_parameters(self) -> str:
    """Return XML string of all available scanner parameters."""
    return await self._ib.reqScannerParametersAsync()
```

---

## Repository Changes

Add to `src/database/repository.py`:

```python
async def get_candidate_by_ticker(self, ticker: str) -> Candidate | None:
    """Check if a ticker already exists in candidates table."""
```

This likely already exists or is trivially added.

---

## Logging

All scanner actions logged via structlog:

```
universe_scan_started    — scan cycle begins
universe_scan_tier       — per-tier scan with result count
universe_scan_filtered   — after pre-filter, how many passed
universe_scan_inserted   — new candidates added
universe_scan_complete   — cycle done with total new count
universe_scan_error      — any IBKR errors during scan
```

---

## Error Handling

- **IBKR scanner not available** — Some account types may not have scanner access. Catch and log, disable scanner gracefully.
- **No results** — Normal for off-market hours. Log and continue.
- **Rate limiting** — 15-min interval is conservative. IBKR allows frequent scanner requests but we don't need more.
- **Scanner timeout** — If `reqScannerSubscription` doesn't return within 10 seconds, cancel and retry next cycle.

---

## Testing

- Unit test `UniverseScanner` with `MockAdapter` that returns synthetic `ScanData`
- Test pre-filter logic (dedup, spread, exchange)
- Test insert flow (new candidates appear in DB with correct tier/exchange)
- Test scan loop starts/stops cleanly
- Integration test: scanner → TickerWatcher → Screener pipeline (synthetic data)

---

## What This Does NOT Do

- Does not replace manual ticker entry (both paths coexist)
- Does not score tickers (that's the existing RuleEngine's job)
- Does not manage L2/T&S subscriptions (that's TickerWatcher's job)
- Does not do technical analysis (that's a future feature)
- Does not filter by stability (that's the Screener's job after historical data loads)

---

## Open Questions (Resolve During Implementation)

1. **Exact `locationCode` for OTC stocks** — Need to call `reqScannerParameters()` to discover available codes. `STK.US.MINOR` is the likely candidate but needs verification.
2. **Best `scanCode`** — Start with `TOP_PERC_GAIN`, test `MOST_ACTIVE` and `HOT_BY_VOLUME`. May need multiple codes per tier.
3. **Spread calculation from scanner results** — `ScanData.contractDetails` may or may not include bid/ask. If not, spread check happens after TickerWatcher subscribes market data.
