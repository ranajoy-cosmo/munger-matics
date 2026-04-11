"""Tests for src/munger_matics/finance/compounding.py.

All expected values are derived from textbook formulas with explicit arithmetic
shown in comments so any future change in precision or rounding can be audited.
"""

from decimal import Decimal

import pytest

from munger_matics.finance.compounding import (
    CompoundingFreq,
    future_value_compound,
    future_value_simple,
    present_value,
)


# ---------------------------------------------------------------------------
# future_value_simple
# ---------------------------------------------------------------------------


def test_simple_interest_three_years() -> None:
    # PV=1000, r=0.05, n=3 → 1000 * (1 + 0.05*3) = 1000 * 1.15 = 1150.00
    result = future_value_simple(Decimal("1000"), Decimal("0.05"), 3)
    assert result == Decimal("1150.00")


def test_simple_interest_zero_rate() -> None:
    # r=0 → FV == PV
    result = future_value_simple(Decimal("500"), Decimal("0"), 10)
    assert result == Decimal("500.00")


def test_simple_interest_zero_periods() -> None:
    # n=0 → FV == PV
    result = future_value_simple(Decimal("750"), Decimal("0.10"), 0)
    assert result == Decimal("750.00")


# ---------------------------------------------------------------------------
# future_value_compound
# ---------------------------------------------------------------------------


def test_compound_annual_one_year() -> None:
    # PV=1000, r=0.05, t=1, m=1 → 1000 * (1.05)^1 = 1050.00
    result = future_value_compound(
        Decimal("1000"), Decimal("0.05"), 1, CompoundingFreq.ANNUAL
    )
    assert result == Decimal("1050.00")


def test_compound_monthly_one_year() -> None:
    # PV=1000, r=0.05, t=1, m=12 → 1000 * (1 + 0.05/12)^12
    # = 1000 * (1.00416667)^12 ≈ 1051.1618979... → rounds to 1051.16
    result = future_value_compound(
        Decimal("1000"), Decimal("0.05"), 1, CompoundingFreq.MONTHLY
    )
    assert result == Decimal("1051.16")


def test_compound_daily_one_year() -> None:
    # PV=1000, r=0.05, t=1, m=365 → 1000 * (1 + 0.05/365)^365
    # ≈ 1000 * 1.05127... ≈ 1051.27
    result = future_value_compound(
        Decimal("1000"), Decimal("0.05"), 1, CompoundingFreq.DAILY
    )
    assert result == Decimal("1051.27")


def test_compound_annual_multiple_years() -> None:
    # PV=2000, r=0.03, t=5, m=1 → 2000 * (1.03)^5 = 2000 * 1.159274... = 2318.55
    result = future_value_compound(
        Decimal("2000"), Decimal("0.03"), 5, CompoundingFreq.ANNUAL
    )
    assert result == Decimal("2318.55")


def test_compound_zero_rate_returns_pv() -> None:
    result = future_value_compound(
        Decimal("5000"), Decimal("0"), 10, CompoundingFreq.MONTHLY
    )
    assert result == Decimal("5000.00")


def test_compound_default_freq_is_annual() -> None:
    # Omitting freq should behave identically to passing ANNUAL
    result_default = future_value_compound(Decimal("1000"), Decimal("0.05"), 1)
    result_annual = future_value_compound(
        Decimal("1000"), Decimal("0.05"), 1, CompoundingFreq.ANNUAL
    )
    assert result_default == result_annual


# ---------------------------------------------------------------------------
# present_value
# ---------------------------------------------------------------------------


def test_pv_is_inverse_of_compound_fv() -> None:
    # PV → FV → PV should round-trip within one cent.
    # Uses MONTHLY compounding over 10 years to exercise the full path.
    pv_original = Decimal("3000.00")
    fv = future_value_compound(
        pv_original, Decimal("0.04"), 10, CompoundingFreq.MONTHLY
    )
    pv_recovered = present_value(fv, Decimal("0.04"), 10, CompoundingFreq.MONTHLY)
    # Rounding at both ends can introduce ±0.01; allow one-cent tolerance.
    assert abs(pv_recovered - pv_original) <= Decimal("0.01")


def test_pv_annual_one_year() -> None:
    # FV=1050, r=0.05, t=1, m=1 → 1050 / 1.05 = 1000.00
    result = present_value(Decimal("1050"), Decimal("0.05"), 1, CompoundingFreq.ANNUAL)
    assert result == Decimal("1000.00")


def test_pv_zero_rate_returns_fv() -> None:
    result = present_value(Decimal("800"), Decimal("0"), 5, CompoundingFreq.ANNUAL)
    assert result == Decimal("800.00")


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_simple_negative_rate_raises() -> None:
    with pytest.raises(ValueError, match="rate"):
        future_value_simple(Decimal("1000"), Decimal("-0.01"), 1)


def test_simple_negative_pv_raises() -> None:
    with pytest.raises(ValueError, match="pv"):
        future_value_simple(Decimal("-1000"), Decimal("0.05"), 1)


def test_compound_negative_rate_raises() -> None:
    with pytest.raises(ValueError, match="annual_rate"):
        future_value_compound(Decimal("1000"), Decimal("-0.05"), 1)


def test_compound_negative_pv_raises() -> None:
    with pytest.raises(ValueError, match="pv"):
        future_value_compound(Decimal("-1000"), Decimal("0.05"), 1)


def test_pv_negative_rate_raises() -> None:
    with pytest.raises(ValueError, match="annual_rate"):
        present_value(Decimal("1050"), Decimal("-0.05"), 1)


def test_pv_negative_fv_raises() -> None:
    with pytest.raises(ValueError, match="fv"):
        present_value(Decimal("-100"), Decimal("0.05"), 1)
