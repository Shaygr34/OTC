"""Event dataclasses for the internal pub/sub bus.

All events are frozen (immutable) and carry a UTC timestamp.
All price fields use Decimal — never float.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True)
class MarketDataEvent:
    ticker: str
    price: Decimal
    bid: Decimal
    ask: Decimal
    volume: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class L2UpdateEvent:
    ticker: str
    bid_levels: tuple[tuple[Decimal, int, str], ...]  # (price, size, mm_id)
    ask_levels: tuple[tuple[Decimal, int, str], ...]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TradeEvent:
    ticker: str
    price: Decimal
    size: int
    side: str  # "bid" | "ask" | "unknown"
    mm_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ScannerHitEvent:
    ticker: str
    price_tier: str
    price: Decimal
    volume: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class AnalysisCompleteEvent:
    ticker: str
    atm_score: Decimal
    stability_score: Decimal
    l2_score: Decimal
    volume_score: Decimal
    dilution_score: Decimal
    ts_score: Decimal
    components_scored: int = 0
    score_detail: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class AlertEvent:
    ticker: str
    alert_type: str  # VOLUME_ANOMALY | BID_COLLAPSE | RATIO_CHANGE
    severity: str    # INFO | WARNING | HIGH | CRITICAL
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class DilutionAlertEvent:
    ticker: str
    dilution_score: int
    severity: str  # WARNING | HIGH_ALERT | CRITICAL
    signals: tuple[str, ...]
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
