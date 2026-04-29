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
