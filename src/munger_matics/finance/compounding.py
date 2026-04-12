from __future__ import annotations

from decimal import Decimal

import math

from munger_matics.finance._common import CompoundingFreq, _quantize, _quantize_rate

__all__ = [
    "CompoundingFreq",
    "future_value_compound",
    "future_value_simple",
    "present_value",
    "required_rate",
    "years_to_target",
]


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


def years_to_target(
    pv: Decimal,
    fv: Decimal,
    annual_rate: Decimal,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> float:
    """Time (in years) for a lump sum to grow from PV to FV under compound interest.

    t = ln(FV / PV) / (m × ln(1 + r/m))

    "How long until my €10K grows to €20K at 5% compounded monthly?"

    Args:
        pv: Present value. Must be > 0.
        fv: Target future value. Must be > 0.
        annual_rate: Annual interest rate as a decimal fraction. Must be > 0.
        freq: Compounding frequency per year. Defaults to ANNUAL.

    Returns:
        Time in years as a float (e.g. 14.21 years).
    """
    if pv <= Decimal(0):
        raise ValueError(f"pv must be > 0, got {pv}")
    if fv <= Decimal(0):
        raise ValueError(f"fv must be > 0, got {fv}")
    if annual_rate <= Decimal(0):
        raise ValueError(f"annual_rate must be > 0, got {annual_rate}")

    m = int(freq)
    r = float(annual_rate)

    t = math.log(float(fv) / float(pv)) / (m * math.log(1.0 + r / m))
    return round(t, 2)


def required_rate(
    pv: Decimal,
    fv: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> Decimal:
    """Annual rate needed for a lump sum to grow from PV to FV in a given time.

    r = m × [(FV / PV)^(1/(m×t)) − 1]

    "What annual return do I need to turn €50K into €100K in 10 years?"

    Args:
        pv: Present value. Must be > 0.
        fv: Target future value. Must be > 0.
        years: Time horizon in years. Must be > 0.
        freq: Compounding frequency per year. Defaults to ANNUAL.

    Returns:
        Nominal annual rate as a decimal fraction, rounded to 6 decimal places.
    """
    if pv <= Decimal(0):
        raise ValueError(f"pv must be > 0, got {pv}")
    if fv <= Decimal(0):
        raise ValueError(f"fv must be > 0, got {fv}")
    if years <= 0:
        raise ValueError(f"years must be > 0, got {years}")

    m = int(freq)
    t = float(years)

    rate = m * ((float(fv) / float(pv)) ** (1.0 / (m * t)) - 1.0)
    return _quantize_rate(rate)
