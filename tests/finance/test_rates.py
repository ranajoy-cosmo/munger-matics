"""Tests for src/munger_matics/finance/rates.py.

All expected values are derived from textbook formulas with explicit arithmetic
shown in comments so any future change in precision or rounding can be audited.
"""

from decimal import Decimal

import pytest

from munger_matics.finance.rates import (
    cagr,
    effective_annual_rate,
    nominal_from_ear,
    real_rate,
)
from munger_matics.finance._common import CompoundingFreq


# ---------------------------------------------------------------------------
# effective_annual_rate
# ---------------------------------------------------------------------------


def test_ear_monthly_compounding() -> None:
    # 5% nominal, monthly: EAR = (1 + 0.05/12)^12 - 1
    # = (1.00416667)^12 - 1 ≈ 0.051162
    result = effective_annual_rate(Decimal("0.05"), CompoundingFreq.MONTHLY)
    assert result == Decimal("0.051162")


def test_ear_quarterly_compounding() -> None:
    # 8% nominal, quarterly: EAR = (1 + 0.08/4)^4 - 1
    # = (1.02)^4 - 1 = 1.08243216 - 1 ≈ 0.082432
    result = effective_annual_rate(Decimal("0.08"), CompoundingFreq.QUARTERLY)
    assert result == Decimal("0.082432")


def test_ear_annual_is_identity() -> None:
    # Annual compounding: EAR = (1 + r/1)^1 - 1 = r
    result = effective_annual_rate(Decimal("0.05"), CompoundingFreq.ANNUAL)
    assert result == Decimal("0.050000")


def test_ear_zero_rate() -> None:
    result = effective_annual_rate(Decimal("0"), CompoundingFreq.MONTHLY)
    assert result == Decimal("0.000000")


def test_ear_negative_rate_raises() -> None:
    with pytest.raises(ValueError, match="nominal_rate"):
        effective_annual_rate(Decimal("-0.05"))


# ---------------------------------------------------------------------------
# nominal_from_ear
# ---------------------------------------------------------------------------


def test_nominal_from_ear_monthly() -> None:
    # EAR = 0.051162, monthly: r_nom = 12 * [(1.051162)^(1/12) - 1]
    # ≈ 12 * 0.004167 ≈ 0.050000
    result = nominal_from_ear(Decimal("0.051162"), CompoundingFreq.MONTHLY)
    assert result == Decimal("0.050000")


def test_nominal_from_ear_annual_is_identity() -> None:
    result = nominal_from_ear(Decimal("0.05"), CompoundingFreq.ANNUAL)
    assert result == Decimal("0.050000")


def test_nominal_from_ear_zero() -> None:
    result = nominal_from_ear(Decimal("0"), CompoundingFreq.MONTHLY)
    assert result == Decimal("0.000000")


def test_nominal_from_ear_negative_raises() -> None:
    with pytest.raises(ValueError, match="ear"):
        nominal_from_ear(Decimal("-0.05"))


def test_ear_nominal_round_trip() -> None:
    # nominal → EAR → nominal should round-trip within rate precision.
    original = Decimal("0.060000")
    ear = effective_annual_rate(original, CompoundingFreq.MONTHLY)
    recovered = nominal_from_ear(ear, CompoundingFreq.MONTHLY)
    assert abs(recovered - original) <= Decimal("0.000001")


# ---------------------------------------------------------------------------
# real_rate
# ---------------------------------------------------------------------------


def test_real_rate_typical() -> None:
    # nominal 8%, inflation 3%: (1.08 / 1.03) - 1 = 0.048544
    result = real_rate(Decimal("0.08"), Decimal("0.03"))
    assert result == Decimal("0.048544")


def test_real_rate_zero_inflation() -> None:
    # No inflation: real == nominal
    result = real_rate(Decimal("0.07"), Decimal("0"))
    assert result == Decimal("0.070000")


def test_real_rate_negative_nominal() -> None:
    # 0% nominal, 3% inflation → negative real return
    # (1.00 / 1.03) - 1 = -0.029126
    result = real_rate(Decimal("0"), Decimal("0.03"))
    assert result == Decimal("-0.029126")


def test_real_rate_deflation() -> None:
    # 5% nominal, -2% inflation (deflation): (1.05 / 0.98) - 1 = 0.071429
    result = real_rate(Decimal("0.05"), Decimal("-0.02"))
    assert result == Decimal("0.071429")


def test_real_rate_inflation_minus_one_raises() -> None:
    with pytest.raises(ValueError, match="inflation_rate"):
        real_rate(Decimal("0.05"), Decimal("-1"))


def test_real_rate_inflation_below_minus_one_raises() -> None:
    with pytest.raises(ValueError, match="inflation_rate"):
        real_rate(Decimal("0.05"), Decimal("-1.5"))


# ---------------------------------------------------------------------------
# cagr
# ---------------------------------------------------------------------------


def test_cagr_growth() -> None:
    # PV=10000, FV=15000, 5 years: (15000/10000)^(1/5) - 1
    # = 1.5^0.2 - 1 ≈ 0.084472
    result = cagr(Decimal("10000"), Decimal("15000"), 5)
    assert result == Decimal("0.084472")


def test_cagr_no_change() -> None:
    # FV == PV → CAGR = 0
    result = cagr(Decimal("5000"), Decimal("5000"), 10)
    assert result == Decimal("0.000000")


def test_cagr_decline() -> None:
    # PV=10000, FV=5000, 3 years: (5000/10000)^(1/3) - 1
    # = 0.5^(1/3) - 1 ≈ -0.206299
    result = cagr(Decimal("10000"), Decimal("5000"), 3)
    assert result == Decimal("-0.206299")


def test_cagr_zero_pv_raises() -> None:
    with pytest.raises(ValueError, match="pv"):
        cagr(Decimal("0"), Decimal("1000"), 5)


def test_cagr_negative_fv_raises() -> None:
    with pytest.raises(ValueError, match="fv"):
        cagr(Decimal("1000"), Decimal("-500"), 5)


def test_cagr_zero_years_raises() -> None:
    with pytest.raises(ValueError, match="years"):
        cagr(Decimal("1000"), Decimal("2000"), 0)


def test_cagr_negative_years_raises() -> None:
    with pytest.raises(ValueError, match="years"):
        cagr(Decimal("1000"), Decimal("2000"), -3)
