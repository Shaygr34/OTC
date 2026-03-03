"""Tests for config/constants.py — classify_mm, tier ranges, get_tier."""

from decimal import Decimal

from config.constants import (
    MM_BAD,
    MM_NEUTRAL,
    MM_RETAIL,
    TIER_RANGES,
    MMClassification,
    PriceTier,
    classify_mm,
    get_tier,
)


class TestClassifyMM:
    def test_bad_mm(self):
        assert classify_mm("MAXM") == MMClassification.BAD
        assert classify_mm("GLED") == MMClassification.BAD
        assert classify_mm("BMAK") == MMClassification.BAD

    def test_retail_mm(self):
        assert classify_mm("ETRF") == MMClassification.RETAIL
        assert classify_mm("NITE") == MMClassification.RETAIL

    def test_neutral_mm(self):
        assert classify_mm("VIRT") == MMClassification.NEUTRAL
        assert classify_mm("CDEL") == MMClassification.NEUTRAL

    def test_unknown_mm(self):
        assert classify_mm("XXXX") == MMClassification.UNKNOWN

    def test_case_insensitive(self):
        assert classify_mm("maxm") == MMClassification.BAD
        assert classify_mm("Etrf") == MMClassification.RETAIL

    def test_whitespace_stripped(self):
        assert classify_mm("  MAXM  ") == MMClassification.BAD

    def test_no_overlap_between_sets(self):
        assert MM_BAD.isdisjoint(MM_RETAIL)
        assert MM_BAD.isdisjoint(MM_NEUTRAL)
        assert MM_RETAIL.isdisjoint(MM_NEUTRAL)


class TestTierRanges:
    def test_all_tiers_have_ranges(self):
        for tier in PriceTier:
            assert tier in TIER_RANGES

    def test_low_bound_less_than_high(self):
        for tier, rng in TIER_RANGES.items():
            assert rng.low < rng.high, f"{tier}: low >= high"


class TestGetTier:
    def test_trip_zero(self):
        assert get_tier(Decimal("0.0001")) == PriceTier.TRIP_ZERO
        assert get_tier(Decimal("0.0005")) == PriceTier.TRIP_ZERO

    def test_trips(self):
        assert get_tier(Decimal("0.0006")) == PriceTier.TRIPS
        assert get_tier(Decimal("0.0009")) == PriceTier.TRIPS

    def test_low_dubs(self):
        assert get_tier(Decimal("0.001")) == PriceTier.LOW_DUBS
        assert get_tier(Decimal("0.003")) == PriceTier.LOW_DUBS

    def test_dubs(self):
        assert get_tier(Decimal("0.005")) == PriceTier.DUBS

    def test_pennies(self):
        assert get_tier(Decimal("0.01")) == PriceTier.PENNIES
        assert get_tier(Decimal("0.03")) == PriceTier.PENNIES

    def test_out_of_range(self):
        assert get_tier(Decimal("0.00001")) is None
        assert get_tier(Decimal("0.05")) is None
        assert get_tier(Decimal("1.00")) is None
