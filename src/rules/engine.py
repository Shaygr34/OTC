"""YAML-driven rule engine — computes ATM probability score from analyzer results.

Consumes results from L2Analyzer, VolumeAnalyzer, TSAnalyzer,
DilutionSentinel, and Screener. Publishes AnalysisCompleteEvent.
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import structlog
import yaml

from config.constants import (
    ATM_MIN_TRADE,
    ATM_MIN_WATCHLIST,
    ATM_WEIGHT_BID_SUPPORT,
    ATM_WEIGHT_CONSISTENT_VOLUME,
    ATM_WEIGHT_DILUTION_CLEAR,
    ATM_WEIGHT_L2_IMBALANCE,
    ATM_WEIGHT_NO_BAD_MM,
    ATM_WEIGHT_NO_VOLUME_ANOMALY,
    ATM_WEIGHT_STABILITY,
    ATM_WEIGHT_TS_RATIO,
)
from src.analysis.dilution import DilutionSentinel
from src.analysis.level2 import L2Analyzer
from src.analysis.time_sales import TSAnalyzer
from src.analysis.volume import VolumeAnalyzer
from src.core.event_bus import EventBus
from src.core.events import AnalysisCompleteEvent, ScannerHitEvent
from src.scanner.screener import Screener

logger = structlog.get_logger(__name__)

_ZERO = Decimal("0")
_ONE = Decimal("1")

_DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "rules.yaml"


@dataclass(frozen=True)
class RuleConfig:
    """Parsed rule configuration from YAML."""

    weight_stability: int
    weight_l2_imbalance: int
    weight_no_bad_mm: int
    weight_no_volume_anomaly: int
    weight_consistent_volume: int
    weight_bid_support: int
    weight_ts_ratio: int
    weight_dilution_clear: int

    l2_imbalance_favorable: Decimal
    l2_imbalance_strong: Decimal
    volume_anomaly_zscore_max: Decimal
    consistent_volume_min_days: int
    ts_ratio_bullish_min: Decimal
    dilution_clear_max: int
    bid_support_min_ratio: Decimal

    min_watchlist: int
    min_trade: int


def load_rules(path: Path | None = None) -> RuleConfig:
    """Load rule configuration from YAML, falling back to constants.py defaults."""
    if path is None:
        path = _DEFAULT_RULES_PATH

    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        scoring = raw.get("scoring", {})
        weights = scoring.get("weights", {})
        thresholds = scoring.get("thresholds", {})
        actions = raw.get("actions", {})

        return RuleConfig(
            weight_stability=weights.get("stability", ATM_WEIGHT_STABILITY),
            weight_l2_imbalance=weights.get("l2_imbalance", ATM_WEIGHT_L2_IMBALANCE),
            weight_no_bad_mm=weights.get("no_bad_mm", ATM_WEIGHT_NO_BAD_MM),
            weight_no_volume_anomaly=weights.get(
                "no_volume_anomaly", ATM_WEIGHT_NO_VOLUME_ANOMALY
            ),
            weight_consistent_volume=weights.get(
                "consistent_volume", ATM_WEIGHT_CONSISTENT_VOLUME
            ),
            weight_bid_support=weights.get("bid_support", ATM_WEIGHT_BID_SUPPORT),
            weight_ts_ratio=weights.get("ts_ratio", ATM_WEIGHT_TS_RATIO),
            weight_dilution_clear=weights.get(
                "dilution_clear", ATM_WEIGHT_DILUTION_CLEAR
            ),
            l2_imbalance_favorable=Decimal(
                str(thresholds.get("l2_imbalance_favorable", "3.0"))
            ),
            l2_imbalance_strong=Decimal(
                str(thresholds.get("l2_imbalance_strong", "5.0"))
            ),
            volume_anomaly_zscore_max=Decimal(
                str(thresholds.get("volume_anomaly_zscore_max", "2.0"))
            ),
            consistent_volume_min_days=int(
                thresholds.get("consistent_volume_min_days", 10)
            ),
            ts_ratio_bullish_min=Decimal(
                str(thresholds.get("ts_ratio_bullish_min", "1.0"))
            ),
            dilution_clear_max=int(thresholds.get("dilution_clear_max", 2)),
            bid_support_min_ratio=Decimal(
                str(thresholds.get("bid_support_min_ratio", "3.0"))
            ),
            min_watchlist=actions.get("watchlist", {}).get(
                "min_score", ATM_MIN_WATCHLIST
            ),
            min_trade=actions.get("trade", {}).get("min_score", ATM_MIN_TRADE),
        )

    # No YAML file — use constants.py defaults
    logger.warning("rules_yaml_not_found", path=str(path))
    return RuleConfig(
        weight_stability=ATM_WEIGHT_STABILITY,
        weight_l2_imbalance=ATM_WEIGHT_L2_IMBALANCE,
        weight_no_bad_mm=ATM_WEIGHT_NO_BAD_MM,
        weight_no_volume_anomaly=ATM_WEIGHT_NO_VOLUME_ANOMALY,
        weight_consistent_volume=ATM_WEIGHT_CONSISTENT_VOLUME,
        weight_bid_support=ATM_WEIGHT_BID_SUPPORT,
        weight_ts_ratio=ATM_WEIGHT_TS_RATIO,
        weight_dilution_clear=ATM_WEIGHT_DILUTION_CLEAR,
        l2_imbalance_favorable=Decimal("3.0"),
        l2_imbalance_strong=Decimal("5.0"),
        volume_anomaly_zscore_max=Decimal("2.0"),
        consistent_volume_min_days=10,
        ts_ratio_bullish_min=Decimal("1.0"),
        dilution_clear_max=2,
        bid_support_min_ratio=Decimal("3.0"),
        min_watchlist=ATM_MIN_WATCHLIST,
        min_trade=ATM_MIN_TRADE,
    )


@dataclass(frozen=True)
class ScoringResult:
    """Detailed breakdown of the ATM probability score."""

    ticker: str
    total_score: Decimal
    stability_score: Decimal
    l2_score: Decimal
    volume_score: Decimal
    dilution_score: Decimal
    ts_score: Decimal
    # Derived labels
    action: str  # "TRADE" | "WATCHLIST" | "PASS"


class RuleEngine:
    """YAML-driven ATM probability scoring engine.

    Subscribes to ScannerHitEvent. For each hit, pulls analyzer results,
    computes a composite score, and publishes AnalysisCompleteEvent.

    Lifecycle:
        1. Construct with EventBus + all analyzer references.
        2. Optionally load custom rules via ``load_rules(path)``.
        3. Call ``start()`` to subscribe to ScannerHitEvent.
        4. Each scanner hit triggers score computation + event publish.
    """

    def __init__(
        self,
        event_bus: EventBus,
        screener: Screener,
        l2_analyzer: L2Analyzer,
        volume_analyzer: VolumeAnalyzer,
        ts_analyzer: TSAnalyzer,
        dilution_sentinel: DilutionSentinel,
        rules: RuleConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._screener = screener
        self._l2 = l2_analyzer
        self._volume = volume_analyzer
        self._ts = ts_analyzer
        self._dilution = dilution_sentinel
        self._rules = rules or load_rules()
        self._results: dict[str, ScoringResult] = {}

    @property
    def rules(self) -> RuleConfig:
        return self._rules

    def start(self) -> None:
        """Subscribe to ScannerHitEvent on the bus."""
        self._event_bus.subscribe(ScannerHitEvent, self._on_scanner_hit)
        logger.info("rule_engine_started")

    def get_result(self, symbol: str) -> ScoringResult | None:
        return self._results.get(symbol)

    async def _on_scanner_hit(self, event: ScannerHitEvent) -> None:
        """Handle a scanner hit — run dilution eval, score, and publish."""
        # Trigger dilution evaluation (pull model)
        await self._dilution.evaluate(event.ticker)
        result = self.score(event.ticker)
        self._results[event.ticker] = result

        # Publish AnalysisCompleteEvent
        analysis_event = AnalysisCompleteEvent(
            ticker=event.ticker,
            atm_score=result.total_score,
            stability_score=result.stability_score,
            l2_score=result.l2_score,
            volume_score=result.volume_score,
            dilution_score=result.dilution_score,
            ts_score=result.ts_score,
        )
        await self._event_bus.publish(analysis_event)

        logger.info(
            "atm_score_computed",
            ticker=event.ticker,
            score=str(result.total_score),
            action=result.action,
        )

    def score(self, symbol: str) -> ScoringResult:
        """Compute ATM probability score from all analyzer results."""
        r = self._rules

        # ── 1) Stability (binary: scanner already validated) ──────
        stability_result = self._screener.get_last_result(symbol)
        if stability_result and stability_result.is_stable:
            stability_pts = Decimal(str(r.weight_stability))
        else:
            stability_pts = _ZERO

        # ── 2) L2 Imbalance (scaled: STRONG=full, FAVORABLE=60%) ─
        l2 = self._l2.get_result(symbol)
        if l2 and l2.imbalance_ratio >= r.l2_imbalance_strong:
            l2_pts = Decimal(str(r.weight_l2_imbalance))
        elif l2 and l2.imbalance_ratio >= r.l2_imbalance_favorable:
            l2_pts = Decimal(str(r.weight_l2_imbalance)) * Decimal("0.6")
        else:
            l2_pts = _ZERO

        # ── 3) No Bad MM on Ask (binary) ─────────────────────────
        if l2 and not l2.has_bad_mm_on_ask:
            bad_mm_pts = Decimal(str(r.weight_no_bad_mm))
        elif l2 is None:
            bad_mm_pts = _ZERO
        else:
            bad_mm_pts = _ZERO

        # ── 4) No Volume Anomaly (binary: zscore below threshold) ─
        vol = self._volume.get_result(symbol)
        if vol and vol.zscore < r.volume_anomaly_zscore_max:
            vol_anomaly_pts = Decimal(str(r.weight_no_volume_anomaly))
        elif vol is None:
            vol_anomaly_pts = _ZERO
        else:
            vol_anomaly_pts = _ZERO

        # ── 5) Consistent Volume (binary: enough active days) ─────
        if vol and vol.active_days >= r.consistent_volume_min_days:
            consistent_vol_pts = Decimal(str(r.weight_consistent_volume))
        else:
            consistent_vol_pts = _ZERO

        # ── 6) Bid Support (binary: imbalance >= favorable) ───────
        if l2 and l2.imbalance_ratio >= r.bid_support_min_ratio:
            bid_support_pts = Decimal(str(r.weight_bid_support))
        else:
            bid_support_pts = _ZERO

        # ── 7) T&S Ratio Bullish (binary) ────────────────────────
        ts = self._ts.get_result(symbol)
        if ts and ts.buy_sell_ratio >= r.ts_ratio_bullish_min and ts.total_trades > 0:
            ts_pts = Decimal(str(r.weight_ts_ratio))
        else:
            ts_pts = _ZERO

        # ── 8) Dilution Clear (binary: score <= clear max) ────────
        dil = self._dilution.get_result(symbol)
        if dil and dil.score <= r.dilution_clear_max:
            dil_pts = Decimal(str(r.weight_dilution_clear))
        else:
            dil_pts = _ZERO

        # ── Composite ────────────────────────────────────────────
        total = (
            stability_pts
            + l2_pts
            + bad_mm_pts
            + vol_anomaly_pts
            + consistent_vol_pts
            + bid_support_pts
            + ts_pts
            + dil_pts
        )

        # Determine action
        if total >= Decimal(str(r.min_trade)):
            action = "TRADE"
        elif total >= Decimal(str(r.min_watchlist)):
            action = "WATCHLIST"
        else:
            action = "PASS"

        # For the AnalysisCompleteEvent, we combine certain sub-scores:
        # volume_score = vol_anomaly + consistent_vol (max 20)
        # l2_score = l2_imbalance + bad_mm + bid_support (max 45)
        return ScoringResult(
            ticker=symbol,
            total_score=total,
            stability_score=stability_pts,
            l2_score=l2_pts + bad_mm_pts + bid_support_pts,
            volume_score=vol_anomaly_pts + consistent_vol_pts,
            dilution_score=dil_pts,
            ts_score=ts_pts,
            action=action,
        )
