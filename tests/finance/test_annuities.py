"""Tests for src/munger_matics/finance/annuities.py.

All expected values are derived from textbook formulas with explicit arithmetic
shown in comments so any future change in precision or rounding can be audited.
"""

from decimal import Decimal

import pytest

from munger_matics.finance._common import CompoundingFreq
from munger_matics.finance.annuities import (
    amortization_schedule,
    annuity_required_rate,
    fv_annuity,
    payment,
    periods_to_target,
    pv_annuity,
)


# ---------------------------------------------------------------------------
# payment
# ---------------------------------------------------------------------------


def test_payment_textbook_mortgage() -> None:
    # $200,000 loan, 6% annual, 30 years, monthly payments.
    # r = 0.06/12 = 0.005, n = 360
    # PMT = 200000 * 0.005 * (1.005)^360 / [(1.005)^360 - 1]
    # (1.005)^360 ≈ 6.02258, PMT ≈ 200000 * 0.005 * 6.02258 / 5.02258
    # ≈ 200000 * 0.005995 ≈ 1199.10
    result = payment(Decimal("200000"), Decimal("0.06"), 30, CompoundingFreq.MONTHLY)
    assert result == Decimal("1199.10")


def test_payment_annual_five_years() -> None:
    # $10,000 loan, 5% annual, 5 years, annual payments.
    # r = 0.05, n = 5
    # PMT = 10000 * 0.05 * (1.05)^5 / [(1.05)^5 - 1]
    # (1.05)^5 = 1.2762816, PMT = 10000 * 0.05 * 1.2762816 / 0.2762816
    # = 10000 * 0.230975 ≈ 2309.75
    result = payment(Decimal("10000"), Decimal("0.05"), 5, CompoundingFreq.ANNUAL)
    assert result == Decimal("2309.75")


def test_payment_zero_rate() -> None:
    # r=0 → PMT = PV / n
    # $12,000 / 12 months = $1,000.00
    result = payment(Decimal("12000"), Decimal("0"), 1, CompoundingFreq.MONTHLY)
    assert result == Decimal("1000.00")


def test_payment_zero_pv() -> None:
    result = payment(Decimal("0"), Decimal("0.05"), 5, CompoundingFreq.ANNUAL)
    assert result == Decimal("0.00")


def test_payment_negative_pv_raises() -> None:
    with pytest.raises(ValueError, match="pv"):
        payment(Decimal("-1000"), Decimal("0.05"), 5)


def test_payment_negative_rate_raises() -> None:
    with pytest.raises(ValueError, match="annual_rate"):
        payment(Decimal("1000"), Decimal("-0.05"), 5)


def test_payment_zero_years_raises() -> None:
    with pytest.raises(ValueError, match="years"):
        payment(Decimal("1000"), Decimal("0.05"), 0)


# ---------------------------------------------------------------------------
# pv_annuity
# ---------------------------------------------------------------------------


def test_pv_annuity_round_trip_with_payment() -> None:
    # PV → PMT → PVA should approximately recover the original PV.
    # PMT is quantized to 2dp, then PVA re-accumulates that rounded value
    # over 360 periods, so drift of a few cents to ~$1 is expected.
    original_pv = Decimal("200000")
    pmt = payment(original_pv, Decimal("0.06"), 30, CompoundingFreq.MONTHLY)
    recovered = pv_annuity(pmt, Decimal("0.06"), 30, CompoundingFreq.MONTHLY)
    assert abs(recovered - original_pv) <= Decimal("1.00")


def test_pv_annuity_zero_rate() -> None:
    # r=0 → PVA = PMT * n = 500 * 60 = 30000.00
    result = pv_annuity(Decimal("500"), Decimal("0"), 5, CompoundingFreq.MONTHLY)
    assert result == Decimal("30000.00")


def test_pv_annuity_annual() -> None:
    # PMT=1000, r=10%, 5 years annual.
    # PVA = 1000 * [(1 - 1.10^-5) / 0.10]
    # 1.10^-5 = 0.620921, PVA = 1000 * (1 - 0.620921) / 0.10 = 1000 * 3.79079
    # ≈ 3790.79
    result = pv_annuity(Decimal("1000"), Decimal("0.10"), 5, CompoundingFreq.ANNUAL)
    assert result == Decimal("3790.79")


def test_pv_annuity_negative_pmt_raises() -> None:
    with pytest.raises(ValueError, match="pmt"):
        pv_annuity(Decimal("-100"), Decimal("0.05"), 5)


# ---------------------------------------------------------------------------
# fv_annuity
# ---------------------------------------------------------------------------


def test_fv_annuity_retirement_savings() -> None:
    # $500/month, 7% annual, 30 years.
    # r = 0.07/12 ≈ 0.005833, n = 360
    # FVA = 500 * [((1.005833)^360 - 1) / 0.005833]
    # (1.005833)^360 ≈ 8.11649, FVA ≈ 500 * (8.11649 - 1) / 0.005833
    # ≈ 500 * 1219.97 ≈ 609,985 (approximate — textbook: $610,000 range)
    result = fv_annuity(Decimal("500"), Decimal("0.07"), 30, CompoundingFreq.MONTHLY)
    # Textbook value: 609,985.41 (varies slightly by precision)
    assert Decimal("609980") < result < Decimal("609990")


def test_fv_annuity_annual() -> None:
    # $1,000/year, 5%, 10 years.
    # FVA = 1000 * [(1.05^10 - 1) / 0.05]
    # 1.05^10 = 1.628895, FVA = 1000 * 0.628895 / 0.05 = 1000 * 12.5779
    # ≈ 12577.89
    result = fv_annuity(Decimal("1000"), Decimal("0.05"), 10, CompoundingFreq.ANNUAL)
    assert result == Decimal("12577.89")


def test_fv_annuity_zero_rate() -> None:
    # r=0 → FVA = PMT * n = 200 * 24 = 4800.00
    result = fv_annuity(Decimal("200"), Decimal("0"), 2, CompoundingFreq.MONTHLY)
    assert result == Decimal("4800.00")


def test_fv_annuity_negative_pmt_raises() -> None:
    with pytest.raises(ValueError, match="pmt"):
        fv_annuity(Decimal("-100"), Decimal("0.05"), 5)


# ---------------------------------------------------------------------------
# periods_to_target
# ---------------------------------------------------------------------------


def test_periods_to_target_from_zero() -> None:
    # Save $1,000/month at 6% annual to reach $100,000.
    # n = ln(1 + 100000 * 0.005 / 1000) / ln(1.005)
    # = ln(1.5) / ln(1.005) = 0.405465 / 0.004988 ≈ 81.3 → ceil = 82
    result = periods_to_target(
        Decimal("100000"),
        Decimal("1000"),
        Decimal("0.06"),
        CompoundingFreq.MONTHLY,
    )
    assert result == 82


def test_periods_to_target_with_initial_balance() -> None:
    # Already have $10,000, save $1,000/month at 6% annual, target $50,000.
    # (1.005)^n = (50000 + 1000/0.005) / (10000 + 1000/0.005)
    # = (50000 + 200000) / (10000 + 200000) = 250000 / 210000 = 1.190476
    # n = ln(1.190476) / ln(1.005) = 0.174353 / 0.004988 ≈ 34.95 → ceil = 35
    result = periods_to_target(
        Decimal("50000"),
        Decimal("1000"),
        Decimal("0.06"),
        CompoundingFreq.MONTHLY,
        initial_pv=Decimal("10000"),
    )
    assert result == 35


def test_periods_to_target_zero_rate() -> None:
    # r=0, target=12000, PMT=500, initial=2000 → (12000-2000)/500 = 20
    result = periods_to_target(
        Decimal("12000"),
        Decimal("500"),
        Decimal("0"),
        CompoundingFreq.MONTHLY,
        initial_pv=Decimal("2000"),
    )
    assert result == 20


def test_periods_to_target_zero_rate_needs_ceiling() -> None:
    # r=0, target=10000, PMT=300, initial=0 → 10000/300 = 33.33 → 34
    result = periods_to_target(
        Decimal("10000"),
        Decimal("300"),
        Decimal("0"),
        CompoundingFreq.MONTHLY,
    )
    assert result == 34


def test_periods_to_target_already_met() -> None:
    # Initial balance >= target → 0 periods needed.
    result = periods_to_target(
        Decimal("50000"),
        Decimal("1000"),
        Decimal("0.06"),
        CompoundingFreq.MONTHLY,
        initial_pv=Decimal("60000"),
    )
    assert result == 0


def test_periods_to_target_negative_target_raises() -> None:
    with pytest.raises(ValueError, match="target_fv"):
        periods_to_target(Decimal("-1000"), Decimal("100"), Decimal("0.05"))


def test_periods_to_target_negative_pmt_raises() -> None:
    with pytest.raises(ValueError, match="pmt"):
        periods_to_target(Decimal("1000"), Decimal("-100"), Decimal("0.05"))


def test_periods_to_target_zero_pmt_raises() -> None:
    with pytest.raises(ValueError, match="pmt"):
        periods_to_target(Decimal("1000"), Decimal("0"), Decimal("0.05"))


# ---------------------------------------------------------------------------
# amortization_schedule
# ---------------------------------------------------------------------------


def test_amortization_three_year_annual() -> None:
    # $3,000 loan, 10% annual, 3 years, annual payments.
    # PMT = 3000 * 0.10 * (1.10)^3 / [(1.10)^3 - 1]
    # = 3000 * 0.10 * 1.331 / 0.331 = 3000 * 0.402115 = 1206.34
    schedule = amortization_schedule(
        Decimal("3000"), Decimal("0.10"), 3, CompoundingFreq.ANNUAL
    )
    assert len(schedule) == 3

    # Period 1: interest = 3000 * 0.10 = 300.00
    row1 = schedule[0]
    assert row1.period == 1
    assert row1.interest_payment == Decimal("300.00")
    assert row1.remaining_balance > Decimal("0")

    # All periods: principal payments sum to original loan.
    total_principal = sum(row.principal_payment for row in schedule)
    assert total_principal == Decimal("3000.00")

    # Last period balance is exactly zero.
    assert schedule[-1].remaining_balance == Decimal("0.00")


def test_amortization_sum_invariants() -> None:
    # For any schedule, each row: payment = principal_payment + interest_payment
    schedule = amortization_schedule(
        Decimal("100000"), Decimal("0.05"), 10, CompoundingFreq.MONTHLY
    )
    for row in schedule:
        assert row.payment == row.principal_payment + row.interest_payment


def test_amortization_principal_sums_to_loan() -> None:
    # Sum of all principal payments must equal the original loan amount.
    principal = Decimal("200000")
    schedule = amortization_schedule(
        principal, Decimal("0.06"), 30, CompoundingFreq.MONTHLY
    )
    total_principal = sum(row.principal_payment for row in schedule)
    assert total_principal == principal


def test_amortization_last_balance_zero() -> None:
    # 30-year monthly mortgage: last row balance must be exactly 0.00.
    schedule = amortization_schedule(
        Decimal("200000"), Decimal("0.06"), 30, CompoundingFreq.MONTHLY
    )
    assert len(schedule) == 360
    assert schedule[-1].remaining_balance == Decimal("0.00")


def test_amortization_first_period_interest() -> None:
    # First period interest = principal * periodic_rate
    # $200,000 at 6% monthly: interest = 200000 * 0.005 = 1000.00
    schedule = amortization_schedule(
        Decimal("200000"), Decimal("0.06"), 30, CompoundingFreq.MONTHLY
    )
    assert schedule[0].interest_payment == Decimal("1000.00")


def test_amortization_zero_rate() -> None:
    # r=0: each period pays principal/n evenly, no interest.
    schedule = amortization_schedule(
        Decimal("1200"), Decimal("0"), 1, CompoundingFreq.MONTHLY
    )
    assert len(schedule) == 12
    for row in schedule:
        assert row.interest_payment == Decimal("0.00")
    total_principal = sum(row.principal_payment for row in schedule)
    assert total_principal == Decimal("1200.00")
    assert schedule[-1].remaining_balance == Decimal("0.00")


def test_amortization_rows_are_frozen() -> None:
    schedule = amortization_schedule(
        Decimal("1000"), Decimal("0.05"), 1, CompoundingFreq.ANNUAL
    )
    with pytest.raises(Exception):
        schedule[0].payment = Decimal("999.99")  # type: ignore[misc]


def test_amortization_negative_principal_raises() -> None:
    with pytest.raises(ValueError, match="principal"):
        amortization_schedule(Decimal("-1000"), Decimal("0.05"), 5)


def test_amortization_zero_principal_raises() -> None:
    with pytest.raises(ValueError, match="principal"):
        amortization_schedule(Decimal("0"), Decimal("0.05"), 5)


def test_amortization_final_payment_adjustment_is_small() -> None:
    # The final payment adjustment (to zero the balance) should be small.
    # Each period quantizes interest/principal to 2dp, so over 360 periods
    # cumulative drift of ~$1 is normal. Allow up to $2.00.
    schedule = amortization_schedule(
        Decimal("200000"), Decimal("0.06"), 30, CompoundingFreq.MONTHLY
    )
    regular_pmt = schedule[0].payment
    final_pmt = schedule[-1].payment
    adjustment = abs(final_pmt - regular_pmt)
    assert adjustment < Decimal("2.00")


# ---------------------------------------------------------------------------
# annuity_required_rate
# ---------------------------------------------------------------------------


def test_annuity_required_rate_from_zero() -> None:
    # Save $500/month for 30 years to reach ~$610K. We know from
    # test_fv_annuity_retirement_savings that 7% annual produces ~$609,985.
    # So the required rate to reach $609985 should be ~0.07.
    result = annuity_required_rate(
        Decimal("609985"),
        Decimal("500"),
        30,
        CompoundingFreq.MONTHLY,
    )
    assert abs(result - Decimal("0.07")) <= Decimal("0.0001")


def test_annuity_required_rate_with_initial_balance() -> None:
    # Have $10K, save $1,000/month for 10 years to reach $200K.
    # Round-trip: compute rate, then verify FV matches target.
    target = Decimal("200000")
    pmt = Decimal("1000")
    years = 10
    pv = Decimal("10000")
    freq = CompoundingFreq.MONTHLY

    rate = annuity_required_rate(target, pmt, years, freq, initial_pv=pv)

    # Verify: PV*(1+r/m)^(m*t) + PMT*[((1+r/m)^(m*t) - 1) / (r/m)]
    r = float(rate) / int(freq)
    n = years * int(freq)
    g = (1.0 + r) ** n
    fv_check = float(pv) * g + float(pmt) * (g - 1.0) / r
    assert abs(fv_check - float(target)) < 1.0


def test_annuity_required_rate_zero_initial() -> None:
    # $1,000/year for 10 years to reach $12,577.89 (the FV annuity at 5%).
    result = annuity_required_rate(
        Decimal("12577.89"),
        Decimal("1000"),
        10,
        CompoundingFreq.ANNUAL,
    )
    assert abs(result - Decimal("0.05")) <= Decimal("0.0001")


def test_annuity_required_rate_low_target() -> None:
    # Target barely above what contributions alone would produce (rate ≈ 0).
    # $100/month for 10 years = $12,000 at 0%. Target $12,100 needs tiny rate.
    result = annuity_required_rate(
        Decimal("12100"),
        Decimal("100"),
        10,
        CompoundingFreq.MONTHLY,
    )
    assert result >= Decimal("0")
    assert result < Decimal("0.01")


def test_annuity_required_rate_negative_target_raises() -> None:
    with pytest.raises(ValueError, match="target_fv"):
        annuity_required_rate(Decimal("-1000"), Decimal("100"), 5)


def test_annuity_required_rate_zero_pmt_raises() -> None:
    with pytest.raises(ValueError, match="pmt"):
        annuity_required_rate(Decimal("10000"), Decimal("0"), 5)


def test_annuity_required_rate_negative_initial_raises() -> None:
    with pytest.raises(ValueError, match="initial_pv"):
        annuity_required_rate(
            Decimal("10000"), Decimal("100"), 5, initial_pv=Decimal("-1000")
        )
