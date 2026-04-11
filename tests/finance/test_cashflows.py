"""Tests for src/munger_matics/finance/cashflows.py.

All expected values are derived from textbook formulas with explicit arithmetic
shown in comments so any future change in precision or rounding can be audited.
"""

from datetime import date
from decimal import Decimal

import pytest

from munger_matics.finance.cashflows import irr, npv, xirr


# ---------------------------------------------------------------------------
# npv
# ---------------------------------------------------------------------------


def test_npv_textbook() -> None:
    # Invest $1000 today, receive $300, $420, $680 over 3 years at 10%.
    # NPV = -1000 + 300/1.10 + 420/1.21 + 680/1.331
    # = -1000 + 272.7273 + 347.1074 + 510.8948 = 130.7295 → 130.73
    result = npv(
        Decimal("0.10"),
        [Decimal("-1000"), Decimal("300"), Decimal("420"), Decimal("680")],
    )
    assert result == Decimal("130.73")


def test_npv_zero_rate() -> None:
    # r=0: NPV = simple sum of cash flows.
    cfs = [Decimal("-1000"), Decimal("300"), Decimal("420"), Decimal("680")]
    result = npv(Decimal("0"), cfs)
    expected = sum(cfs)
    assert result == Decimal(str(expected))


def test_npv_single_cashflow() -> None:
    # Period 0 is not discounted.
    result = npv(Decimal("0.10"), [Decimal("5000")])
    assert result == Decimal("5000.00")


def test_npv_empty_raises() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        npv(Decimal("0.10"), [])


def test_npv_rate_minus_one_raises() -> None:
    with pytest.raises(ValueError, match="rate"):
        npv(Decimal("-1"), [Decimal("-100"), Decimal("200")])


# ---------------------------------------------------------------------------
# irr
# ---------------------------------------------------------------------------


def test_irr_simple_two_cashflows() -> None:
    # Invest $100, receive $110 one period later → IRR = 10%.
    result = irr([Decimal("-100"), Decimal("110")])
    assert result == Decimal("0.100000")


def test_irr_textbook() -> None:
    # Same cash flows as the NPV textbook example.
    # IRR is the rate where NPV = 0.
    cfs = [Decimal("-1000"), Decimal("300"), Decimal("420"), Decimal("680")]
    result = irr(cfs)
    # Verify round-trip: NPV at this IRR should be near zero.
    npv_at_irr = npv(result, cfs)
    assert abs(npv_at_irr) <= Decimal("0.01")


def test_irr_exact_double() -> None:
    # Invest $1000, receive $2000 after 1 period → IRR = 100%.
    result = irr([Decimal("-1000"), Decimal("2000")])
    assert result == Decimal("1.000000")


def test_irr_all_positive_raises() -> None:
    with pytest.raises(ValueError, match="positive and one negative"):
        irr([Decimal("100"), Decimal("200")])


def test_irr_all_negative_raises() -> None:
    with pytest.raises(ValueError, match="positive and one negative"):
        irr([Decimal("-100"), Decimal("-200")])


def test_irr_too_few_cashflows_raises() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        irr([Decimal("-100")])


def test_irr_round_trip_npv_near_zero() -> None:
    # A more complex cash flow pattern.
    cfs = [
        Decimal("-5000"),
        Decimal("1200"),
        Decimal("1400"),
        Decimal("1600"),
        Decimal("1800"),
    ]
    rate = irr(cfs)
    npv_at_irr = npv(rate, cfs)
    assert abs(npv_at_irr) <= Decimal("0.01")


# ---------------------------------------------------------------------------
# xirr
# ---------------------------------------------------------------------------


def test_xirr_simple_one_year() -> None:
    # Invest $10,000 on Jan 1, receive $11,000 on Jan 1 next year → 10%.
    result = xirr(
        [Decimal("-10000"), Decimal("11000")],
        [date(2025, 1, 1), date(2026, 1, 1)],
    )
    assert result == Decimal("0.100000")


def test_xirr_multiple_cashflows() -> None:
    # Invest $10,000, receive $5,500 after 6 months and $5,500 after 1 year.
    cfs = [Decimal("-10000"), Decimal("5500"), Decimal("5500")]
    ds = [date(2025, 1, 1), date(2025, 7, 1), date(2026, 1, 1)]
    result = xirr(cfs, ds)
    # Round-trip: compute the day-count NPV at the returned rate.
    r = float(result)
    d0 = ds[0]
    npv_check = sum(
        float(cf) / (1.0 + r) ** ((d - d0).days / 365.0) for cf, d in zip(cfs, ds)
    )
    assert abs(npv_check) < 0.01


def test_xirr_matches_irr_for_annual_spacing() -> None:
    # When dates are exactly one year apart, XIRR should match IRR.
    cfs = [Decimal("-1000"), Decimal("300"), Decimal("420"), Decimal("680")]
    ds = [date(2025, 1, 1), date(2026, 1, 1), date(2027, 1, 1), date(2028, 1, 1)]
    xirr_result = xirr(cfs, ds)
    irr_result = irr(cfs)
    # Allow small difference due to 365-day year fraction vs exact periods.
    assert abs(xirr_result - irr_result) <= Decimal("0.001000")


def test_xirr_mismatched_lengths_raises() -> None:
    with pytest.raises(ValueError, match="same length"):
        xirr(
            [Decimal("-100"), Decimal("110")],
            [date(2025, 1, 1)],
        )


def test_xirr_all_positive_raises() -> None:
    with pytest.raises(ValueError, match="positive and one negative"):
        xirr(
            [Decimal("100"), Decimal("200")],
            [date(2025, 1, 1), date(2026, 1, 1)],
        )


def test_xirr_too_few_cashflows_raises() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        xirr([Decimal("-100")], [date(2025, 1, 1)])
