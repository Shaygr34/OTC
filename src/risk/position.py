"""Position sizing — 5% max per position, 2% max loss.

Pure computation from RiskSettings + current portfolio value.
No event subscriptions; called directly by other modules.
"""

from dataclasses import dataclass
from decimal import Decimal

import structlog

from config.settings import RiskSettings

logger = structlog.get_logger(__name__)

_ZERO = Decimal("0")


@dataclass(frozen=True)
class PositionSize:
    """Computed position sizing for a trade."""

    max_position_value: Decimal  # portfolio x max_position_pct
    max_shares: int              # floor(max_position_value / entry_price)
    max_loss_value: Decimal      # portfolio x max_loss_pct
    portfolio_value: Decimal


class PositionSizer:
    """Computes position sizes from risk settings.

    Recalculate portfolio_value at start of each month.
    """

    def __init__(self, settings: RiskSettings | None = None) -> None:
        self._settings = settings or RiskSettings()
        self._portfolio_value = self._settings.portfolio_value

    @property
    def portfolio_value(self) -> Decimal:
        return self._portfolio_value

    def update_portfolio_value(self, value: Decimal) -> None:
        """Update portfolio value (call at start of each month)."""
        if value <= _ZERO:
            raise ValueError(f"Portfolio value must be positive, got {value}")
        self._portfolio_value = value
        logger.info("portfolio_value_updated", value=str(value))

    def compute(self, entry_price: Decimal) -> PositionSize:
        """Compute position sizing for a given entry price."""
        if entry_price <= _ZERO:
            raise ValueError(f"Entry price must be positive, got {entry_price}")

        max_pos_value = self._portfolio_value * self._settings.max_position_pct
        max_shares = int(max_pos_value / entry_price)
        max_loss = self._portfolio_value * self._settings.max_loss_pct

        logger.debug(
            "position_sized",
            entry_price=str(entry_price),
            max_value=str(max_pos_value),
            max_shares=max_shares,
            max_loss=str(max_loss),
        )

        return PositionSize(
            max_position_value=max_pos_value,
            max_shares=max_shares,
            max_loss_value=max_loss,
            portfolio_value=self._portfolio_value,
        )

    def compute_with_ohi(
        self, entry_price: Decimal, ohi_sizing_factor: Decimal,
    ) -> PositionSize:
        """Compute position sizing adjusted by OHI factor.

        ohi_sizing_factor: 1.0 = full size, 0.5 = half, 0 = blocked.
        """
        if ohi_sizing_factor <= _ZERO:
            return PositionSize(
                max_position_value=_ZERO,
                max_shares=0,
                max_loss_value=_ZERO,
                portfolio_value=self._portfolio_value,
            )

        base = self.compute(entry_price)
        adjusted_value = base.max_position_value * ohi_sizing_factor
        adjusted_shares = int(adjusted_value / entry_price)
        adjusted_loss = base.max_loss_value * ohi_sizing_factor

        return PositionSize(
            max_position_value=adjusted_value,
            max_shares=adjusted_shares,
            max_loss_value=adjusted_loss,
            portfolio_value=self._portfolio_value,
        )
