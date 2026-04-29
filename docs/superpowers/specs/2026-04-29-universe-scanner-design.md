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
    locationCode="STK.US",         # Broad US; post-filter for OTC exchanges
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

**Note on `locationCode`:** Using `STK.US` (broad) with exchange post-filter for OTC (PINK/GREY). `STK.US.MINOR` may also work but is unverified. Implementation task #1 calls `reqScannerParametersAsync()` to discover exact available codes and will upgrade to a more specific code if one exists.

**Note on `scanCode`:** `MOST_ACTIVE` is the primary choice — we want liquid OTC stocks. Fallbacks: `TOP_TRADE_COUNT`, `HOT_BY_VOLUME`. Multiple scan codes can be run per tier if one code doesn't surface enough OTC results.

---

## Pre-Filters

Before inserting a discovered ticker into the candidates table:

1. **Dedup check** — Skip if ticker already exists in candidates table (any status). Uses `repo.get_candidate_by_ticker()`.

2. **Spread check** — Deferred. `ScanData` does not contain bid/ask prices. Spread filtering happens downstream after TickerWatcher subscribes market data and the Screener evaluates. Future enhancement: add spread-based rejection to Screener.

3. **Exchange validation** — Only accept tickers on PINK or GREY exchanges. Check `contractDetails.contract.primaryExchange` first, fall back to `contractDetails.validExchanges` (comma-separated string like `"SMART,PINK"`).

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

## Broker Adapter Changes

Add abstract method to `src/broker/adapter.py`, implement in `src/broker/ibkr.py` and `src/broker/mock.py`:

```python
async def request_scanner(self, subscription: ScannerSubscription) -> list:
    """Run a one-shot scanner request. Uses reqScannerDataAsync which
    subscribes, awaits the initial data dump, cancels, and returns."""
    self._ensure_connected()
    results = await asyncio.wait_for(
        self._ib.reqScannerDataAsync(subscription),
        timeout=10.0,
    )
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
    """Check if a ticker already exists in candidates table (any status)."""
```

This does NOT exist currently — must be implemented. Trivial SELECT query.

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

1. **Exact `locationCode` for OTC stocks** — First implementation task calls `reqScannerParametersAsync()` to discover available codes. Using `STK.US` with post-filter as safe default.
2. **Best `scanCode`** — Start with `MOST_ACTIVE`, test alternatives. May need multiple codes per tier.
3. **Spread check** — RESOLVED: Deferred to downstream. `ScanData` has no bid/ask. Spread filtering will happen after market data subscription.
4. **IBKR scanner access on this account type** — Must verify scanner API works on Eldar's account. Test during implementation task #1.
5. **Volume filter threshold** — `aboveVolume=10000` may be too aggressive for TRIPS. Consider tier-dependent: TRIPS=1000, DUBS=10000.
