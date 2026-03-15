"""HistoryLoader — seeds the Screener with historical daily bars on startup.

Fetches 30-day daily bars from the broker for each watchlist symbol and
feeds them to the Screener so stability metrics work from the first tick.
"""

from decimal import Decimal

import structlog

from src.broker.adapter import BrokerAdapter
from src.scanner.screener import Screener
from src.scanner.stability import DailyBar
from src.scanner.watchlist import WatchlistEntry

logger = structlog.get_logger(__name__)


class HistoryLoader:
    """One-shot loader that seeds historical bars into the Screener."""

    @staticmethod
    async def seed(
        watchlist: list[WatchlistEntry],
        adapter: BrokerAdapter,
        screener: Screener,
    ) -> dict[str, int]:
        """Fetch and load historical bars for all watchlist symbols.

        Returns a dict of {ticker: bars_loaded} for logging.
        """
        loaded: dict[str, int] = {}
        for entry in watchlist:
            try:
                bars = await adapter.request_historical_bars(
                    symbol=entry.ticker,
                    exchange=entry.exchange,
                )
                for bar_data in bars:
                    daily_bar = DailyBar(
                        open=Decimal(str(bar_data["open"])),
                        high=Decimal(str(bar_data["high"])),
                        low=Decimal(str(bar_data["low"])),
                        close=Decimal(str(bar_data["close"])),
                        volume=int(bar_data["volume"]),
                    )
                    screener.add_daily_bar(entry.ticker, daily_bar)
                loaded[entry.ticker] = len(bars)
                logger.info(
                    "history_seeded",
                    ticker=entry.ticker,
                    bars=len(bars),
                )
            except Exception:
                logger.exception("history_seed_failed", ticker=entry.ticker)
                loaded[entry.ticker] = 0

        logger.info(
            "history_seed_complete",
            symbols=len(watchlist),
            total_bars=sum(loaded.values()),
        )
        return loaded
