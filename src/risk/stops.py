"""Five layered stop conditions — any one triggers exit.

1. Hard dollar stop: loss exceeds 2% of account
2. Volatility stop: price drops 2x ATR below entry
3. Time stop: exceeds max hold time per tier
4. Dilution stop: dilution score >= 3
5. L2 collapse stop: total bid size < 30% of entry bid size
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

import structlog

from config.constants import (
    BID_COLLAPSE_EXIT_PCT,
    DILUTION_EXIT_TRIGGER,
    MAX_HOLD_DAYS_DUBS,
    MAX_HOLD_DAYS_PENNIES,
    MAX_HOLD_DAYS_TRIPS_OVERNIGHT,
    MAX_HOLD_HOURS_TRIPS_INTRADAY,
    VOLATILITY_STOP_ATR_MULTIPLIER,
    PriceTier,
)

logger = structlog.get_logger(__name__)

_ZERO = Decimal("0")


class StopReason(StrEnum):
    HARD_DOLLAR = "HARD_DOLLAR"
    VOLATILITY = "VOLATILITY"
    TIME = "TIME"
    DILUTION = "DILUTION"
    L2_COLLAPSE = "L2_COLLAPSE"


@dataclass(frozen=True)
class StopCheck:
    """Result of checking all stop conditions."""

    should_exit: bool
    triggered: tuple[StopReason, ...]
    details: dict[str, str]


@dataclass(frozen=True)
class PositionContext:
    """Context needed to evaluate stop conditions for a position."""

    ticker: str
    tier: PriceTier
    entry_price: Decimal
    current_price: Decimal
    shares: int
    entry_time: datetime
    current_time: datetime
    portfolio_value: Decimal
    max_loss_pct: Decimal  # from RiskSettings
    atr: Decimal           # average true range
    dilution_score: int
    current_bid_shares: int
    entry_bid_shares: int
    is_intraday: bool = True  # distinguish trips intraday vs overnight


class StopManager:
    """Evaluates 5 layered stop conditions against a position."""

    def check(self, ctx: PositionContext) -> StopCheck:
        """Evaluate all stop conditions. Any trigger → exit."""
        triggered: list[StopReason] = []
        details: dict[str, str] = {}

        # 1. Hard dollar stop
        if self._check_hard_dollar(ctx):
            triggered.append(StopReason.HARD_DOLLAR)
            loss = (ctx.entry_price - ctx.current_price) * Decimal(str(ctx.shares))
            max_loss = ctx.portfolio_value * ctx.max_loss_pct
            details["hard_dollar"] = f"loss={loss}, max={max_loss}"

        # 2. Volatility stop
        if self._check_volatility(ctx):
            triggered.append(StopReason.VOLATILITY)
            stop_price = ctx.entry_price - (ctx.atr * VOLATILITY_STOP_ATR_MULTIPLIER)
            details["volatility"] = (
                f"price={ctx.current_price}, stop={stop_price}, "
                f"atr={ctx.atr}"
            )

        # 3. Time stop
        if self._check_time(ctx):
            triggered.append(StopReason.TIME)
            held = ctx.current_time - ctx.entry_time
            max_hold = self._get_max_hold(ctx.tier, ctx.is_intraday)
            details["time"] = f"held={held}, max={max_hold}"

        # 4. Dilution stop
        if self._check_dilution(ctx):
            triggered.append(StopReason.DILUTION)
            details["dilution"] = f"score={ctx.dilution_score}"

        # 5. L2 collapse stop
        if self._check_l2_collapse(ctx):
            triggered.append(StopReason.L2_COLLAPSE)
            if ctx.entry_bid_shares > 0:
                ratio = (
                    Decimal(str(ctx.current_bid_shares))
                    / Decimal(str(ctx.entry_bid_shares))
                )
            else:
                ratio = _ZERO
            details["l2_collapse"] = (
                f"current={ctx.current_bid_shares}, "
                f"entry={ctx.entry_bid_shares}, ratio={ratio}"
            )

        should_exit = len(triggered) > 0

        if should_exit:
            logger.warning(
                "stop_triggered",
                ticker=ctx.ticker,
                reasons=[r.value for r in triggered],
                details=details,
            )

        return StopCheck(
            should_exit=should_exit,
            triggered=tuple(triggered),
            details=details,
        )

    def _check_hard_dollar(self, ctx: PositionContext) -> bool:
        """Loss exceeds max_loss_pct of portfolio."""
        if ctx.current_price >= ctx.entry_price:
            return False
        loss = (ctx.entry_price - ctx.current_price) * Decimal(str(ctx.shares))
        max_loss = ctx.portfolio_value * ctx.max_loss_pct
        return loss > max_loss

    def _check_volatility(self, ctx: PositionContext) -> bool:
        """Price dropped 2x ATR below entry."""
        if ctx.atr <= _ZERO:
            return False
        stop_price = ctx.entry_price - (ctx.atr * VOLATILITY_STOP_ATR_MULTIPLIER)
        return ctx.current_price < stop_price

    def _check_time(self, ctx: PositionContext) -> bool:
        """Held beyond max hold time for this tier."""
        max_hold = self._get_max_hold(ctx.tier, ctx.is_intraday)
        held = ctx.current_time - ctx.entry_time
        return held > max_hold

    def _check_dilution(self, ctx: PositionContext) -> bool:
        """Dilution score at or above exit trigger."""
        return ctx.dilution_score >= DILUTION_EXIT_TRIGGER

    def _check_l2_collapse(self, ctx: PositionContext) -> bool:
        """Bid shares dropped below 30% of entry bid shares."""
        if ctx.entry_bid_shares <= 0:
            return False
        ratio = (
            Decimal(str(ctx.current_bid_shares))
            / Decimal(str(ctx.entry_bid_shares))
        )
        return ratio < BID_COLLAPSE_EXIT_PCT

    @staticmethod
    def _get_max_hold(tier: PriceTier, is_intraday: bool) -> timedelta:
        """Return max hold duration for a tier."""
        if tier in (PriceTier.TRIP_ZERO, PriceTier.TRIPS):
            if is_intraday:
                return timedelta(hours=MAX_HOLD_HOURS_TRIPS_INTRADAY)
            return timedelta(days=MAX_HOLD_DAYS_TRIPS_OVERNIGHT)
        if tier in (PriceTier.LOW_DUBS, PriceTier.DUBS):
            return timedelta(days=MAX_HOLD_DAYS_DUBS)
        # PENNIES
        return timedelta(days=MAX_HOLD_DAYS_PENNIES)
