"""Pydantic v2 models for cross-module data exchange.

All models are frozen (immutable) to prevent accidental mutation downstream.
All financial fields use Decimal — never float.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class L2Level(BaseModel):
    model_config = ConfigDict(frozen=True)

    price: Decimal
    size: int
    mm_id: str


class L2Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    timestamp: datetime
    bid_levels: tuple[L2Level, ...]
    ask_levels: tuple[L2Level, ...]
    imbalance_ratio: Decimal
    total_bid_shares: int
    total_ask_shares: int


class Trade(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    timestamp: datetime
    price: Decimal
    size: int
    side: str  # "bid" | "ask" | "unknown"
    mm_id: str = ""


class CandidateScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    atm_score: Decimal
    stability_score: Decimal
    l2_score: Decimal
    volume_score: Decimal
    dilution_score: Decimal
    ts_score: Decimal


class OHIScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: Decimal
    components: dict[str, Decimal]
