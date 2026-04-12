from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from munger_matics.finance._common import _newton_solve, _quantize, _quantize_rate

__all__ = [
    "irr",
    "npv",
    "xirr",
]


def _validate_sign_change(cashflows: Sequence[Decimal]) -> None:
    """Raise ValueError unless cashflows contain at least one positive and one negative value."""
    has_pos = any(cf > 0 for cf in cashflows)
    has_neg = any(cf < 0 for cf in cashflows)
    if not (has_pos and has_neg):
        raise ValueError(
            "cashflows must contain at least one positive and one negative value"
        )


def npv(rate: Decimal, cashflows: Sequence[Decimal]) -> Decimal:
    """Net Present Value of a series of periodic cash flows.

    NPV = Σ CF_t / (1+r)^t  for t = 0, 1, 2, ...

    The first cash flow (period 0) is not discounted.

    Args:
        rate: Discount rate per period as a decimal fraction. Must be > -1.
        cashflows: Sequence of cash flows, starting at period 0.
                   Must have at least 1 element.

    Returns:
        Net present value rounded to the nearest cent.
    """
    if len(cashflows) < 1:
        raise ValueError("cashflows must have at least 1 element")
    if rate <= Decimal("-1"):
        raise ValueError(f"rate must be > -1, got {rate}")

    r = float(rate)
    total = 0.0
    for t, cf in enumerate(cashflows):
        total += float(cf) / (1.0 + r) ** t

    return _quantize(total)


def irr(
    cashflows: Sequence[Decimal],
    guess: Decimal = Decimal("0.10"),
    tolerance: Decimal = Decimal("0.000001"),
    max_iterations: int = 100,
) -> Decimal:
    """Internal Rate of Return for periodic cash flows.

    Finds the rate r where NPV(r, cashflows) = 0 using Newton-Raphson.

    Args:
        cashflows: Sequence of cash flows at regular intervals.
                   Must have at least 2 elements and contain at least one
                   positive and one negative value.
        guess: Initial rate estimate. Defaults to 10%.
        tolerance: Convergence threshold on |NPV|.
        max_iterations: Maximum solver iterations.

    Returns:
        IRR as a decimal fraction, rounded to 6 decimal places.
    """
    if len(cashflows) < 2:
        raise ValueError("cashflows must have at least 2 elements")
    _validate_sign_change(cashflows)

    cfs = [float(cf) for cf in cashflows]

    def npv_fn(r: float) -> float:
        return sum(cf / (1.0 + r) ** t for t, cf in enumerate(cfs))

    def dnpv_fn(r: float) -> float:
        return sum(-t * cf / (1.0 + r) ** (t + 1) for t, cf in enumerate(cfs))

    rate = _newton_solve(
        npv_fn, dnpv_fn, float(guess), float(tolerance), max_iterations
    )
    return _quantize_rate(rate)


def xirr(
    cashflows: Sequence[Decimal],
    dates: Sequence[date],
    guess: Decimal = Decimal("0.10"),
    tolerance: Decimal = Decimal("0.000001"),
    max_iterations: int = 100,
) -> Decimal:
    """Extended Internal Rate of Return for cash flows at irregular dates.

    Like IRR, but discounts each cash flow by the actual time elapsed
    (in year-fractions) from the first date:

        NPV = Σ CF_i / (1+r)^y_i   where y_i = (d_i − d_0).days / 365.0

    Args:
        cashflows: Cash flow amounts. Must have at least 2 elements and
                   contain at least one positive and one negative value.
        dates: Corresponding dates for each cash flow. Must have the same
               length as cashflows.
        guess: Initial rate estimate. Defaults to 10%.
        tolerance: Convergence threshold on |NPV|.
        max_iterations: Maximum solver iterations.

    Returns:
        XIRR as a decimal fraction, rounded to 6 decimal places.
    """
    if len(cashflows) != len(dates):
        raise ValueError(
            f"cashflows and dates must have the same length, "
            f"got {len(cashflows)} and {len(dates)}"
        )
    if len(cashflows) < 2:
        raise ValueError("cashflows must have at least 2 elements")
    _validate_sign_change(cashflows)

    cfs = [float(cf) for cf in cashflows]
    d0 = dates[0]
    year_fracs = [(d - d0).days / 365.0 for d in dates]

    def npv_fn(r: float) -> float:
        return sum(cf / (1.0 + r) ** y for cf, y in zip(cfs, year_fracs))

    def dnpv_fn(r: float) -> float:
        return sum(-y * cf / (1.0 + r) ** (y + 1) for cf, y in zip(cfs, year_fracs))

    rate = _newton_solve(
        npv_fn, dnpv_fn, float(guess), float(tolerance), max_iterations
    )
    return _quantize_rate(rate)
