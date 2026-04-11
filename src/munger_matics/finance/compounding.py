from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from enum import IntEnum


class CompoundingFreq(IntEnum):
    """Number of compounding periods per year."""

    ANNUAL = 1
    MONTHLY = 12
    DAILY = 365


_CENT = Decimal("0.01")


def _quantize(value: float) -> Decimal:
    # Precision note: fractional exponentiation is computed via float (Python's
    # Decimal does not support non-integer powers). The result is rounded to the
    # nearest cent using ROUND_HALF_UP at the point of return. Intermediate
    # rounding is deliberately avoided; only the final output is rounded.
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


def future_value_simple(
    pv: Decimal,
    rate: Decimal,
    periods: int,
) -> Decimal:
    """Future value under simple (non-compounding) interest.

    FV = PV * (1 + r * n)

    Args:
        pv: Present value. Must be >= 0.
        rate: Periodic interest rate as a decimal fraction (e.g. 0.05 for 5%).
              Must be >= 0.
        periods: Number of periods.

    Returns:
        Future value rounded to the nearest cent.
    """
    if pv < Decimal(0):
        raise ValueError(f"pv must be >= 0, got {pv}")
    if rate < Decimal(0):
        raise ValueError(f"rate must be >= 0, got {rate}")

    fv = float(pv) * (1.0 + float(rate) * periods)
    return _quantize(fv)


def future_value_compound(
    pv: Decimal,
    annual_rate: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> Decimal:
    """Future value under compound interest.

    FV = PV * (1 + r/m)^(m*t)

    where r is the annual rate, m is the compounding frequency, and t is time
    in years.

    Args:
        pv: Present value. Must be >= 0.
        annual_rate: Annual interest rate as a decimal fraction (e.g. 0.05 for 5%).
                     Must be >= 0.
        years: Investment horizon in years. May be fractional.
        freq: Compounding frequency per year. Defaults to ANNUAL.

    Returns:
        Future value rounded to the nearest cent.
    """
    if pv < Decimal(0):
        raise ValueError(f"pv must be >= 0, got {pv}")
    if annual_rate < Decimal(0):
        raise ValueError(f"annual_rate must be >= 0, got {annual_rate}")

    m = int(freq)
    r = float(annual_rate)
    t = float(years)

    fv = float(pv) * (1.0 + r / m) ** (m * t)
    return _quantize(fv)


def present_value(
    fv: Decimal,
    annual_rate: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> Decimal:
    """Present value: the amount needed today to reach a given future value.

    PV = FV / (1 + r/m)^(m*t)

    This is the exact inverse of future_value_compound.

    Args:
        fv: Target future value. Must be >= 0.
        annual_rate: Annual interest rate as a decimal fraction (e.g. 0.05 for 5%).
                     Must be >= 0.
        years: Investment horizon in years. May be fractional.
        freq: Compounding frequency per year. Defaults to ANNUAL.

    Returns:
        Present value rounded to the nearest cent.
    """
    if fv < Decimal(0):
        raise ValueError(f"fv must be >= 0, got {fv}")
    if annual_rate < Decimal(0):
        raise ValueError(f"annual_rate must be >= 0, got {annual_rate}")

    m = int(freq)
    r = float(annual_rate)
    t = float(years)

    pv = float(fv) / (1.0 + r / m) ** (m * t)
    return _quantize(pv)
