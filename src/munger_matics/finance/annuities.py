from __future__ import annotations

import math
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from munger_matics.finance._common import (
    CompoundingFreq,
    _newton_solve,
    _quantize,
    _quantize_rate,
)

__all__ = [
    "AmortizationRow",
    "amortization_schedule",
    "annuity_required_rate",
    "fv_annuity",
    "payment",
    "periods_to_target",
    "pv_annuity",
]


class AmortizationRow(BaseModel):
    """Single period in an amortization schedule."""

    model_config = ConfigDict(frozen=True)

    period: int
    payment: Decimal
    principal_payment: Decimal
    interest_payment: Decimal
    remaining_balance: Decimal


def payment(
    pv: Decimal,
    annual_rate: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> Decimal:
    """Periodic payment for a fixed-rate loan or annuity (ordinary annuity).

    PMT = PV × r(1+r)^n / [(1+r)^n − 1]

    where r = annual_rate / freq, n = years × freq.

    "What's my monthly mortgage payment on a €300K loan at 3.5% over 25 years?"

    Args:
        pv: Present value (loan principal). Must be >= 0.
        annual_rate: Annual interest rate as a decimal fraction. Must be >= 0.
        years: Loan term in years. Must be > 0.
        freq: Payment and compounding frequency. Defaults to ANNUAL.

    Returns:
        Periodic payment rounded to the nearest cent.
    """
    if pv < Decimal(0):
        raise ValueError(f"pv must be >= 0, got {pv}")
    if annual_rate < Decimal(0):
        raise ValueError(f"annual_rate must be >= 0, got {annual_rate}")
    if years <= 0:
        raise ValueError(f"years must be > 0, got {years}")

    m = int(freq)
    r = float(annual_rate) / m
    n = float(years) * m

    if r == 0.0:
        return _quantize(float(pv) / n)

    factor = (1.0 + r) ** n
    pmt = float(pv) * r * factor / (factor - 1.0)
    return _quantize(pmt)


def pv_annuity(
    pmt: Decimal,
    annual_rate: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> Decimal:
    """Present value of an ordinary annuity (stream of equal payments).

    PVA = PMT × [(1 − (1+r)^(−n)) / r]

    "How much do I need saved to withdraw €2,000/month for 25 years?"

    Args:
        pmt: Periodic payment amount. Must be >= 0.
        annual_rate: Annual interest rate as a decimal fraction. Must be >= 0.
        years: Number of years of payments. Must be > 0.
        freq: Payment and compounding frequency. Defaults to ANNUAL.

    Returns:
        Present value rounded to the nearest cent.
    """
    if pmt < Decimal(0):
        raise ValueError(f"pmt must be >= 0, got {pmt}")
    if annual_rate < Decimal(0):
        raise ValueError(f"annual_rate must be >= 0, got {annual_rate}")
    if years <= 0:
        raise ValueError(f"years must be > 0, got {years}")

    m = int(freq)
    r = float(annual_rate) / m
    n = float(years) * m

    if r == 0.0:
        return _quantize(float(pmt) * n)

    pva = float(pmt) * (1.0 - (1.0 + r) ** (-n)) / r
    return _quantize(pva)


def fv_annuity(
    pmt: Decimal,
    annual_rate: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> Decimal:
    """Future value of an ordinary annuity (stream of equal payments).

    FVA = PMT × [((1+r)^n − 1) / r]

    "If I save €500/month at 6% for 30 years, what will I have?"

    Args:
        pmt: Periodic payment amount. Must be >= 0.
        annual_rate: Annual interest rate as a decimal fraction. Must be >= 0.
        years: Number of years of contributions. Must be > 0.
        freq: Payment and compounding frequency. Defaults to ANNUAL.

    Returns:
        Future value rounded to the nearest cent.
    """
    if pmt < Decimal(0):
        raise ValueError(f"pmt must be >= 0, got {pmt}")
    if annual_rate < Decimal(0):
        raise ValueError(f"annual_rate must be >= 0, got {annual_rate}")
    if years <= 0:
        raise ValueError(f"years must be > 0, got {years}")

    m = int(freq)
    r = float(annual_rate) / m
    n = float(years) * m

    if r == 0.0:
        return _quantize(float(pmt) * n)

    fva = float(pmt) * ((1.0 + r) ** n - 1.0) / r
    return _quantize(fva)


def periods_to_target(
    target_fv: Decimal,
    pmt: Decimal,
    annual_rate: Decimal,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
    initial_pv: Decimal = Decimal("0"),
) -> int:
    """Number of whole periods needed to reach a savings target.

    Solves: PV×(1+r)^n + PMT×[(1+r)^n − 1]/r = target  for n.

    Rearranging: (1+r)^n = (target + PMT/r) / (PV + PMT/r)
    so n = ln(numerator / denominator) / ln(1+r).

    When initial_pv is 0, simplifies to n = ln(1 + target×r/PMT) / ln(1+r).

    "I have €10K saved and put away €500/month at 5% — how many months
    until I reach €50K?"

    Args:
        target_fv: Target future value. Must be > 0.
        pmt: Periodic contribution. Must be > 0.
        annual_rate: Annual interest rate as a decimal fraction. Must be >= 0.
        freq: Contribution and compounding frequency. Defaults to ANNUAL.
        initial_pv: Starting balance. Must be >= 0. Defaults to 0.

    Returns:
        Number of whole periods (ceiling), as an int.
    """
    if target_fv <= Decimal(0):
        raise ValueError(f"target_fv must be > 0, got {target_fv}")
    if pmt <= Decimal(0):
        raise ValueError(f"pmt must be > 0, got {pmt}")
    if annual_rate < Decimal(0):
        raise ValueError(f"annual_rate must be >= 0, got {annual_rate}")
    if initial_pv < Decimal(0):
        raise ValueError(f"initial_pv must be >= 0, got {initial_pv}")

    pv = float(initial_pv)
    target = float(target_fv)
    p = float(pmt)

    # If the initial balance already meets or exceeds the target, zero periods.
    if pv >= target:
        return 0

    m = int(freq)
    r = float(annual_rate) / m

    if r == 0.0:
        # Simple: each period adds pmt, starting from initial_pv.
        return math.ceil((target - pv) / p)

    # (1+r)^n = (target + pmt/r) / (pv + pmt/r)
    numerator = target + p / r
    denominator = pv + p / r

    if denominator <= 0.0:
        raise ValueError("Cannot reach target: initial_pv + pmt/rate is non-positive")

    n = math.log(numerator / denominator) / math.log(1.0 + r)
    return math.ceil(n)


def amortization_schedule(
    principal: Decimal,
    annual_rate: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> list[AmortizationRow]:
    """Generate a period-by-period loan amortization schedule.

    Each row shows how much of the payment goes to interest vs principal,
    and the remaining balance. The final payment is adjusted so the balance
    reaches exactly zero (handles cumulative rounding).

    Args:
        principal: Loan amount. Must be > 0.
        annual_rate: Annual interest rate as a decimal fraction. Must be >= 0.
        years: Loan term in years. Must be > 0.
        freq: Payment and compounding frequency. Defaults to ANNUAL.

    Returns:
        List of AmortizationRow, one per period.
    """
    if principal <= Decimal(0):
        raise ValueError(f"principal must be > 0, got {principal}")
    if annual_rate < Decimal(0):
        raise ValueError(f"annual_rate must be >= 0, got {annual_rate}")
    if years <= 0:
        raise ValueError(f"years must be > 0, got {years}")

    m = int(freq)
    r = float(annual_rate) / m
    n = round(float(years) * m)
    pmt = payment(principal, annual_rate, years, freq)

    balance = principal
    rows: list[AmortizationRow] = []

    for period in range(1, n + 1):
        interest = _quantize(float(balance) * r)

        if period == n:
            # Final period: adjust so balance lands exactly on zero.
            principal_part = balance
            final_pmt = principal_part + interest
            rows.append(
                AmortizationRow(
                    period=period,
                    payment=final_pmt,
                    principal_payment=principal_part,
                    interest_payment=interest,
                    remaining_balance=Decimal("0.00"),
                )
            )
        else:
            principal_part = pmt - interest
            balance = balance - principal_part
            rows.append(
                AmortizationRow(
                    period=period,
                    payment=pmt,
                    principal_payment=principal_part,
                    interest_payment=interest,
                    remaining_balance=balance,
                )
            )

    return rows


def annuity_required_rate(
    target_fv: Decimal,
    pmt: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
    initial_pv: Decimal = Decimal("0"),
    guess: Decimal = Decimal("0.05"),
    tolerance: Decimal = Decimal("0.000001"),
    max_iterations: int = 200,
) -> Decimal:
    """Annual rate needed to reach a target with regular contributions.

    Solves: PV×(1+r)^n + PMT×[(1+r)^n − 1]/r = target  for the annual rate.

    No closed-form solution exists; uses Newton-Raphson.

    "I have €10K, save €500/month, want €100K in 10 years — what return
    do I need?"

    Args:
        target_fv: Target future value. Must be > 0.
        pmt: Periodic contribution. Must be > 0.
        years: Time horizon in years. Must be > 0.
        freq: Contribution and compounding frequency. Defaults to ANNUAL.
        initial_pv: Starting balance. Must be >= 0. Defaults to 0.
        guess: Initial rate estimate. Defaults to 5%.
        tolerance: Convergence threshold.
        max_iterations: Maximum solver iterations.

    Returns:
        Nominal annual rate as a decimal fraction, rounded to 6 decimal places.
    """
    if target_fv <= Decimal(0):
        raise ValueError(f"target_fv must be > 0, got {target_fv}")
    if pmt <= Decimal(0):
        raise ValueError(f"pmt must be > 0, got {pmt}")
    if years <= 0:
        raise ValueError(f"years must be > 0, got {years}")
    if initial_pv < Decimal(0):
        raise ValueError(f"initial_pv must be >= 0, got {initial_pv}")

    pv = float(initial_pv)
    target = float(target_fv)
    p = float(pmt)
    m = int(freq)
    n = float(years) * m

    # f(r) = PV*(1+r)^n + PMT*[(1+r)^n - 1]/r - target = 0
    # where r is the periodic rate (annual_rate / freq).
    #
    # f'(r) = PV*n*(1+r)^(n-1)
    #       + PMT * [n*r*(1+r)^(n-1) - (1+r)^n + 1] / r^2

    def f(r: float) -> float:
        if abs(r) < 1e-12:
            # At r≈0: FV ≈ PV + PMT*n
            return pv + p * n - target
        g = (1.0 + r) ** n
        return pv * g + p * (g - 1.0) / r - target

    def df(r: float) -> float:
        if abs(r) < 1e-12:
            # Derivative at r≈0 (linear approximation):
            # d/dr[PV*(1+r)^n] ≈ PV*n
            # d/dr[PMT*n] ≈ PMT*n*(n-1)/2 (Taylor expansion of FVA)
            return pv * n + p * n * (n - 1.0) / 2.0
        g = (1.0 + r) ** n
        dg = n * (1.0 + r) ** (n - 1.0)
        return pv * dg + p * (r * dg - g + 1.0) / (r * r)

    periodic_rate = _newton_solve(
        f, df, float(guess) / m, float(tolerance), max_iterations
    )
    annual_rate = periodic_rate * m
    return _quantize_rate(annual_rate)
