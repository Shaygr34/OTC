"""Tests for the YAML-driven rule engine (Phase 5).

Covers: YAML loading, scoring logic per component, composite score,
action thresholds (WATCHLIST/TRADE/PASS), AnalysisCompleteEvent publishing.
"""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import yaml

from config.constants import (
    ATM_MIN_TRADE,
    ATM_MIN_WATCHLIST,
    ATM_WEIGHT_BID_SUPPORT,
    ATM_WEIGHT_CONSISTENT_VOLUME,
    ATM_WEIGHT_L2_IMBALANCE,
    ATM_WEIGHT_NO_BAD_MM,
    ATM_WEIGHT_NO_VOLUME_ANOMALY,
    ATM_WEIGHT_STABILITY,
    PriceTier,
)
from src.analysis.dilution import DilutionAnalysis, DilutionSentinel
from src.analysis.level2 import L2Analysis, L2Analyzer
from src.analysis.time_sales import TSAnalysis, TSAnalyzer
from src.analysis.volume import VolumeAnalysis, VolumeAnalyzer
from src.core.event_bus import EventBus
from src.core.events import AnalysisCompleteEvent, ScannerHitEvent
from src.rules.engine import RuleConfig, RuleEngine, load_rules
from src.scanner.screener import Screener
from src.scanner.stability import StabilityResult

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def screener(bus):
    return Screener(bus)


@pytest.fixture
def l2_analyzer(bus):
    return L2Analyzer(bus)


@pytest.fixture
def volume_analyzer(bus):
    return VolumeAnalyzer(bus)


@pytest.fixture
def ts_analyzer(bus):
    return TSAnalyzer(bus)


@pytest.fixture
def dilution_sentinel(bus, l2_analyzer, volume_analyzer, ts_analyzer):
    return DilutionSentinel(bus, l2_analyzer, volume_analyzer, ts_analyzer)


@pytest.fixture
def engine(bus, screener, l2_analyzer, volume_analyzer, ts_analyzer, dilution_sentinel):
    return RuleEngine(
        event_bus=bus,
        screener=screener,
        l2_analyzer=l2_analyzer,
        volume_analyzer=volume_analyzer,
        ts_analyzer=ts_analyzer,
        dilution_sentinel=dilution_sentinel,
    )


def _inject_l2(l2_analyzer: L2Analyzer, ticker: str, analysis: L2Analysis) -> None:
    """Directly inject an L2Analysis result."""
    l2_analyzer._results[ticker] = analysis


def _inject_volume(
    volume_analyzer: VolumeAnalyzer, ticker: str, analysis: VolumeAnalysis
) -> None:
    volume_analyzer._results[ticker] = analysis


def _inject_ts(ts_analyzer: TSAnalyzer, ticker: str, analysis: TSAnalysis) -> None:
    ts_analyzer._results[ticker] = analysis


def _inject_dilution(
    dilution_sentinel: DilutionSentinel, ticker: str, analysis: DilutionAnalysis
) -> None:
    dilution_sentinel._results[ticker] = analysis


def _inject_stability(screener: Screener, ticker: str, result: StabilityResult) -> None:
    screener._last_result[ticker] = result


def _make_stable_result() -> StabilityResult:
    return StabilityResult(
        is_stable=True,
        tier=PriceTier.TRIPS,
        active_days=20,
        zero_volume_days=0,
        cv=Decimal("0.10"),
        natr=Decimal("0.10"),
        bb_width=Decimal("0.20"),
        price_range_ratio=Decimal("0.20"),
    )


def _make_strong_l2(ticker: str = "ABCD") -> L2Analysis:
    return L2Analysis(
        ticker=ticker,
        imbalance_ratio=Decimal("6.0"),
        imbalance_label="STRONG",
        total_bid_shares=600000,
        total_ask_shares=100000,
        has_bad_mm_on_ask=False,
    )


def _make_clean_volume(ticker: str = "ABCD") -> VolumeAnalysis:
    return VolumeAnalysis(
        ticker=ticker,
        current_volume=50000,
        mean_volume=Decimal("45000"),
        std_volume=Decimal("5000"),
        zscore=Decimal("1.0"),
        rvol=Decimal("1.1"),
        anomaly_level="NORMAL",
        active_days=18,
        zero_volume_days=2,
        low_activity_warning=False,
    )


def _make_bullish_ts(ticker: str = "ABCD") -> TSAnalysis:
    return TSAnalysis(
        ticker=ticker,
        total_trades=100,
        bid_hits=30,
        ask_hits=70,
        unknown_trades=0,
        buy_sell_ratio=Decimal("2.33"),
        is_bullish=True,
    )


def _make_clear_dilution(ticker: str = "ABCD") -> DilutionAnalysis:
    return DilutionAnalysis(
        ticker=ticker,
        score=0,
        severity="CLEAR",
        should_exit=False,
        signals=(),
        has_bad_mm=False,
    )


def _setup_perfect_candidate(
    screener, l2_analyzer, volume_analyzer, ts_analyzer, dilution_sentinel,
    ticker: str = "ABCD",
) -> None:
    """Inject all analyzer results for a perfect-score candidate."""
    _inject_stability(screener, ticker, _make_stable_result())
    _inject_l2(l2_analyzer, ticker, _make_strong_l2(ticker))
    _inject_volume(volume_analyzer, ticker, _make_clean_volume(ticker))
    _inject_ts(ts_analyzer, ticker, _make_bullish_ts(ticker))
    _inject_dilution(dilution_sentinel, ticker, _make_clear_dilution(ticker))


# ── YAML Loading Tests ───────────────────────────────────────────


class TestLoadRules:
    def test_loads_from_project_yaml(self):
        """Default rules.yaml should load correctly."""
        config = load_rules()
        assert config.weight_stability == ATM_WEIGHT_STABILITY
        assert config.weight_l2_imbalance == ATM_WEIGHT_L2_IMBALANCE
        assert config.min_watchlist == ATM_MIN_WATCHLIST
        assert config.min_trade == ATM_MIN_TRADE

    def test_falls_back_to_constants_when_no_yaml(self, tmp_path):
        """When YAML doesn't exist, use constants.py defaults."""
        config = load_rules(tmp_path / "nonexistent.yaml")
        assert config.weight_stability == ATM_WEIGHT_STABILITY
        assert config.min_watchlist == ATM_MIN_WATCHLIST

    def test_custom_yaml_overrides(self, tmp_path):
        """Custom YAML values override constants."""
        custom = {
            "scoring": {
                "weights": {"stability": 25, "l2_imbalance": 30},
                "thresholds": {"l2_imbalance_favorable": "4.0"},
            },
            "actions": {
                "watchlist": {"min_score": 60},
                "trade": {"min_score": 75},
            },
        }
        path = tmp_path / "custom.yaml"
        path.write_text(yaml.dump(custom))

        config = load_rules(path)
        assert config.weight_stability == 25
        assert config.weight_l2_imbalance == 30
        assert config.l2_imbalance_favorable == Decimal("4.0")
        assert config.min_watchlist == 60
        assert config.min_trade == 75
        # Non-overridden values fall back
        assert config.weight_no_bad_mm == ATM_WEIGHT_NO_BAD_MM

    def test_partial_yaml_fills_defaults(self, tmp_path):
        """A YAML with only some keys fills the rest from defaults."""
        partial = {"scoring": {"weights": {"stability": 20}}}
        path = tmp_path / "partial.yaml"
        path.write_text(yaml.dump(partial))

        config = load_rules(path)
        assert config.weight_stability == 20
        assert config.weight_l2_imbalance == ATM_WEIGHT_L2_IMBALANCE

    def test_empty_yaml_uses_defaults(self, tmp_path):
        """An empty YAML file uses all defaults."""
        path = tmp_path / "empty.yaml"
        path.write_text("")

        config = load_rules(path)
        assert config.weight_stability == ATM_WEIGHT_STABILITY


# ── Scoring Component Tests ──────────────────────────────────────


class TestScoringComponents:
    def test_stability_full_when_stable(self, engine, screener):
        _inject_stability(screener, "ABCD", _make_stable_result())
        result = engine.score("ABCD")
        assert result.stability_score == Decimal(str(ATM_WEIGHT_STABILITY))

    def test_stability_zero_when_unstable(self, engine, screener):
        unstable = StabilityResult(
            is_stable=False, tier=PriceTier.TRIPS, active_days=5,
            zero_volume_days=25, cv=Decimal("0.80"), natr=Decimal("0.80"),
            bb_width=Decimal("0.90"), price_range_ratio=Decimal("0.90"),
        )
        _inject_stability(screener, "ABCD", unstable)
        result = engine.score("ABCD")
        assert result.stability_score == Decimal("0")

    def test_stability_zero_when_no_result(self, engine):
        result = engine.score("ABCD")
        assert result.stability_score == Decimal("0")

    def test_l2_full_when_strong(self, engine, l2_analyzer):
        _inject_l2(l2_analyzer, "ABCD", _make_strong_l2())
        result = engine.score("ABCD")
        # l2_score includes l2_imbalance + no_bad_mm + bid_support
        l2_imb = Decimal(str(ATM_WEIGHT_L2_IMBALANCE))
        no_mm = Decimal(str(ATM_WEIGHT_NO_BAD_MM))
        bid_sup = Decimal(str(ATM_WEIGHT_BID_SUPPORT))
        assert result.l2_score == l2_imb + no_mm + bid_sup

    def test_l2_60pct_when_favorable(self, engine, l2_analyzer):
        favorable = L2Analysis(
            ticker="ABCD",
            imbalance_ratio=Decimal("3.5"),
            imbalance_label="FAVORABLE",
            total_bid_shares=350000,
            total_ask_shares=100000,
            has_bad_mm_on_ask=False,
        )
        _inject_l2(l2_analyzer, "ABCD", favorable)
        result = engine.score("ABCD")
        expected_l2 = Decimal(str(ATM_WEIGHT_L2_IMBALANCE)) * Decimal("0.6")
        no_mm = Decimal(str(ATM_WEIGHT_NO_BAD_MM))
        bid_sup = Decimal(str(ATM_WEIGHT_BID_SUPPORT))
        assert result.l2_score == expected_l2 + no_mm + bid_sup

    def test_l2_zero_when_insufficient(self, engine, l2_analyzer):
        insufficient = L2Analysis(
            ticker="ABCD",
            imbalance_ratio=Decimal("1.5"),
            imbalance_label="INSUFFICIENT",
            total_bid_shares=150000,
            total_ask_shares=100000,
            has_bad_mm_on_ask=False,
        )
        _inject_l2(l2_analyzer, "ABCD", insufficient)
        result = engine.score("ABCD")
        # l2_imbalance=0, no_bad_mm=15, bid_support=0
        assert result.l2_score == Decimal(str(ATM_WEIGHT_NO_BAD_MM))

    def test_bad_mm_zero_points(self, engine, l2_analyzer):
        bad_mm = L2Analysis(
            ticker="ABCD",
            imbalance_ratio=Decimal("6.0"),
            imbalance_label="STRONG",
            total_bid_shares=600000,
            total_ask_shares=100000,
            has_bad_mm_on_ask=True,
            bad_mm_list=["MAXM"],
        )
        _inject_l2(l2_analyzer, "ABCD", bad_mm)
        result = engine.score("ABCD")
        l2_imb = Decimal(str(ATM_WEIGHT_L2_IMBALANCE))
        bid_sup = Decimal(str(ATM_WEIGHT_BID_SUPPORT))
        # no_bad_mm = 0
        assert result.l2_score == l2_imb + bid_sup

    def test_volume_anomaly_zero_when_high_zscore(self, engine, volume_analyzer):
        anomaly = VolumeAnalysis(
            ticker="ABCD",
            current_volume=500000,
            mean_volume=Decimal("45000"),
            std_volume=Decimal("5000"),
            zscore=Decimal("3.5"),
            rvol=Decimal("11.1"),
            anomaly_level="EXTREME",
            active_days=18,
            zero_volume_days=2,
            low_activity_warning=False,
        )
        _inject_volume(volume_analyzer, "ABCD", anomaly)
        result = engine.score("ABCD")
        # vol_anomaly = 0 (zscore > 2.0), consistent_vol = 10 (active_days=18)
        assert result.volume_score == Decimal(str(ATM_WEIGHT_CONSISTENT_VOLUME))

    def test_consistent_volume_zero_when_few_days(self, engine, volume_analyzer):
        low_days = VolumeAnalysis(
            ticker="ABCD",
            current_volume=50000,
            mean_volume=Decimal("45000"),
            std_volume=Decimal("5000"),
            zscore=Decimal("1.0"),
            rvol=Decimal("1.1"),
            anomaly_level="NORMAL",
            active_days=5,
            zero_volume_days=15,
            low_activity_warning=True,
        )
        _inject_volume(volume_analyzer, "ABCD", low_days)
        result = engine.score("ABCD")
        # vol_anomaly = 10, consistent_vol = 0 (active_days < 10)
        assert result.volume_score == Decimal(str(ATM_WEIGHT_NO_VOLUME_ANOMALY))

    def test_ts_zero_when_bearish(self, engine, ts_analyzer):
        bearish = TSAnalysis(
            ticker="ABCD",
            total_trades=100,
            bid_hits=70,
            ask_hits=30,
            unknown_trades=0,
            buy_sell_ratio=Decimal("0.43"),
            is_bullish=False,
        )
        _inject_ts(ts_analyzer, "ABCD", bearish)
        result = engine.score("ABCD")
        assert result.ts_score == Decimal("0")

    def test_ts_zero_when_no_trades(self, engine, ts_analyzer):
        empty = TSAnalysis(
            ticker="ABCD",
            total_trades=0,
            bid_hits=0,
            ask_hits=0,
            unknown_trades=0,
            buy_sell_ratio=Decimal("0"),
            is_bullish=False,
        )
        _inject_ts(ts_analyzer, "ABCD", empty)
        result = engine.score("ABCD")
        assert result.ts_score == Decimal("0")

    def test_dilution_zero_when_warning(self, engine, dilution_sentinel):
        warning = DilutionAnalysis(
            ticker="ABCD",
            score=4,
            severity="WARNING",
            should_exit=True,
            signals=("Volume spike: z=3.5",),
            has_bad_mm=False,
        )
        _inject_dilution(dilution_sentinel, "ABCD", warning)
        result = engine.score("ABCD")
        assert result.dilution_score == Decimal("0")


# ── Composite Score Tests ─────────────────────────────────────────


class TestCompositeScore:
    def test_perfect_score_is_100(
        self, engine, screener, l2_analyzer, volume_analyzer, ts_analyzer,
        dilution_sentinel,
    ):
        _setup_perfect_candidate(
            screener, l2_analyzer, volume_analyzer, ts_analyzer, dilution_sentinel
        )
        result = engine.score("ABCD")
        assert result.total_score == Decimal("100")
        assert result.action == "TRADE"

    def test_zero_score_when_no_data(self, engine):
        result = engine.score("NODATA")
        assert result.total_score == Decimal("0")
        assert result.action == "PASS"

    def test_watchlist_threshold(
        self, engine, screener, l2_analyzer, volume_analyzer, dilution_sentinel,
    ):
        """Score of exactly 70 → WATCHLIST."""
        # stability(15) + l2_strong(20) + no_bad_mm(15) + bid_support(10) + dilution(10)
        # = 70. No volume, no T&S.
        _inject_stability(screener, "ABCD", _make_stable_result())
        _inject_l2(l2_analyzer, "ABCD", _make_strong_l2())
        _inject_dilution(dilution_sentinel, "ABCD", _make_clear_dilution())
        result = engine.score("ABCD")
        assert result.total_score == Decimal("70")
        assert result.action == "WATCHLIST"

    def test_just_below_watchlist_is_pass(
        self, engine, screener, l2_analyzer,
    ):
        """Score below 70 → PASS."""
        # stability(15) + l2_strong(20) + no_bad_mm(15) + bid_support(10) = 60
        _inject_stability(screener, "ABCD", _make_stable_result())
        _inject_l2(l2_analyzer, "ABCD", _make_strong_l2())
        result = engine.score("ABCD")
        assert result.total_score == Decimal("60")
        assert result.action == "PASS"

    def test_trade_threshold(
        self, engine, screener, l2_analyzer, volume_analyzer,
        ts_analyzer, dilution_sentinel,
    ):
        """Score of exactly 80 → TRADE."""
        # stability(15) + l2_strong(20) + no_bad_mm(15) + bid_support(10)
        # + ts(10) + dilution(10) = 80. No volume components.
        _inject_stability(screener, "ABCD", _make_stable_result())
        _inject_l2(l2_analyzer, "ABCD", _make_strong_l2())
        _inject_ts(ts_analyzer, "ABCD", _make_bullish_ts())
        _inject_dilution(dilution_sentinel, "ABCD", _make_clear_dilution())
        result = engine.score("ABCD")
        assert result.total_score == Decimal("80")
        assert result.action == "TRADE"


# ── Event Integration Tests ──────────────────────────────────────


class TestEventIntegration:
    async def test_scanner_hit_triggers_scoring_and_publish(
        self, bus, engine, screener, l2_analyzer, volume_analyzer,
        ts_analyzer, dilution_sentinel,
    ):
        """ScannerHitEvent → score computed → AnalysisCompleteEvent published."""
        _setup_perfect_candidate(
            screener, l2_analyzer, volume_analyzer, ts_analyzer, dilution_sentinel
        )
        engine.start()

        received: list[AnalysisCompleteEvent] = []
        bus.subscribe(AnalysisCompleteEvent, AsyncMock(side_effect=received.append))

        event = ScannerHitEvent(
            ticker="ABCD",
            price_tier="TRIPS",
            price=Decimal("0.0003"),
            volume=50000,
        )
        await bus.publish(event)

        assert len(received) == 1
        assert received[0].ticker == "ABCD"
        assert received[0].atm_score == Decimal("100")

    async def test_dilution_evaluated_before_scoring(
        self, bus, engine, screener, l2_analyzer, volume_analyzer,
        ts_analyzer, dilution_sentinel,
    ):
        """Dilution sentinel is called during scanner hit processing."""
        _inject_stability(screener, "ABCD", _make_stable_result())
        _inject_l2(l2_analyzer, "ABCD", _make_strong_l2())
        engine.start()

        event = ScannerHitEvent(
            ticker="ABCD",
            price_tier="TRIPS",
            price=Decimal("0.0003"),
            volume=50000,
        )
        await bus.publish(event)

        # Dilution sentinel should have been evaluated
        dil = dilution_sentinel.get_result("ABCD")
        assert dil is not None

    async def test_result_stored_after_scoring(
        self, bus, engine, screener, l2_analyzer, volume_analyzer,
        ts_analyzer, dilution_sentinel,
    ):
        """get_result() returns the last scoring result."""
        _setup_perfect_candidate(
            screener, l2_analyzer, volume_analyzer, ts_analyzer, dilution_sentinel
        )
        engine.start()

        event = ScannerHitEvent(
            ticker="ABCD",
            price_tier="TRIPS",
            price=Decimal("0.0003"),
            volume=50000,
        )
        await bus.publish(event)

        result = engine.get_result("ABCD")
        assert result is not None
        assert result.total_score == Decimal("100")
        assert result.action == "TRADE"


# ── Custom Rules Tests ───────────────────────────────────────────


class TestCustomRules:
    def test_custom_weights_change_score(
        self, bus, screener, l2_analyzer, volume_analyzer,
        ts_analyzer, dilution_sentinel,
    ):
        """Custom rules with different weights produce different scores."""
        custom = RuleConfig(
            weight_stability=30,  # doubled
            weight_l2_imbalance=20,
            weight_no_bad_mm=15,
            weight_no_volume_anomaly=10,
            weight_consistent_volume=10,
            weight_bid_support=10,
            weight_ts_ratio=10,
            weight_dilution_clear=10,
            l2_imbalance_favorable=Decimal("3.0"),
            l2_imbalance_strong=Decimal("5.0"),
            volume_anomaly_zscore_max=Decimal("2.0"),
            consistent_volume_min_days=10,
            ts_ratio_bullish_min=Decimal("1.0"),
            dilution_clear_max=2,
            bid_support_min_ratio=Decimal("3.0"),
            min_watchlist=70,
            min_trade=80,
        )
        engine = RuleEngine(
            bus, screener, l2_analyzer, volume_analyzer,
            ts_analyzer, dilution_sentinel, rules=custom,
        )

        _inject_stability(screener, "ABCD", _make_stable_result())
        result = engine.score("ABCD")
        assert result.stability_score == Decimal("30")

    def test_stricter_thresholds_fail_borderline(
        self, bus, screener, l2_analyzer, volume_analyzer,
        ts_analyzer, dilution_sentinel,
    ):
        """Stricter L2 threshold makes a FAVORABLE ratio score 0."""
        custom = RuleConfig(
            weight_stability=15,
            weight_l2_imbalance=20,
            weight_no_bad_mm=15,
            weight_no_volume_anomaly=10,
            weight_consistent_volume=10,
            weight_bid_support=10,
            weight_ts_ratio=10,
            weight_dilution_clear=10,
            l2_imbalance_favorable=Decimal("5.0"),  # stricter
            l2_imbalance_strong=Decimal("8.0"),      # much stricter
            volume_anomaly_zscore_max=Decimal("2.0"),
            consistent_volume_min_days=10,
            ts_ratio_bullish_min=Decimal("1.0"),
            dilution_clear_max=2,
            bid_support_min_ratio=Decimal("5.0"),    # stricter
            min_watchlist=70,
            min_trade=80,
        )
        engine = RuleEngine(
            bus, screener, l2_analyzer, volume_analyzer,
            ts_analyzer, dilution_sentinel, rules=custom,
        )

        # L2 ratio of 4.0 — below the new favorable threshold of 5.0
        borderline = L2Analysis(
            ticker="ABCD",
            imbalance_ratio=Decimal("4.0"),
            imbalance_label="FAVORABLE",
            total_bid_shares=400000,
            total_ask_shares=100000,
            has_bad_mm_on_ask=False,
        )
        _inject_l2(l2_analyzer, "ABCD", borderline)
        result = engine.score("ABCD")
        # l2_imbalance = 0 (below 5.0), no_bad_mm = 15, bid_support = 0
        assert result.l2_score == Decimal("15")


# ── RuleEngine Properties ────────────────────────────────────────


class TestRuleEngineProperties:
    def test_rules_property(self, engine):
        assert engine.rules.weight_stability == ATM_WEIGHT_STABILITY

    def test_get_result_none_for_unknown(self, engine):
        assert engine.get_result("UNKNOWN") is None
