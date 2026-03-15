"""Watchlist loader — reads target symbols from config/watchlist.yaml."""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class WatchlistEntry:
    ticker: str
    exchange: str = "PINK"


def load_watchlist(path: str | Path | None = None) -> list[WatchlistEntry]:
    """Load watchlist entries from YAML file.

    Returns an empty list if the file doesn't exist or has no symbols.
    """
    if path is None:
        path = Path(__file__).resolve().parents[2] / "config" / "watchlist.yaml"
    path = Path(path)

    if not path.exists():
        return []

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    symbols = data.get("symbols") or []
    return [
        WatchlistEntry(
            ticker=entry["ticker"].upper(),
            exchange=entry.get("exchange", "PINK").upper(),
        )
        for entry in symbols
        if isinstance(entry, dict) and "ticker" in entry
    ]
