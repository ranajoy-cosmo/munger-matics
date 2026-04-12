from __future__ import annotations

from decimal import Decimal

from munger_matics.finance._common import CompoundingFreq, _quantize_rate

__all__ = [
    "cagr",
    "effective_annual_rate",
    "nominal_from_ear",
    "real_rate",
]


def effective_annual_rate(
    nominal_rate: Decimal,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> Decimal:
    """Convert a nominal (stated) annual rate to an effective annual rate.

    EAR = (1 + r_nom / m)^m − 1

    A 5% rate compounded monthly actually costs 5.116% per year.

    Args:
        nominal_rate: Nominal annual rate as a decimal fraction (e.g. 0.05 for 5%).
                      Must be >= 0.
        freq: Compounding frequency per year. Defaults to ANNUAL.

    Returns:
        Effective annual rate rounded to 6 decimal places.
    """
    if nominal_rate < Decimal(0):
        raise ValueError(f"nominal_rate must be >= 0, got {nominal_rate}")

    m = int(freq)
    r = float(nominal_rate)

    ear = (1.0 + r / m) ** m - 1.0
    return _quantize_rate(ear)


def nominal_from_ear(
    ear: Decimal,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> Decimal:
    """Convert an effective annual rate back to a nominal (stated) rate.

    r_nom = m × [(1 + EAR)^(1/m) − 1]

    Args:
        ear: Effective annual rate as a decimal fraction. Must be >= 0.
        freq: Compounding frequency per year. Defaults to ANNUAL.

    Returns:
        Nominal annual rate rounded to 6 decimal places.
    """
    if ear < Decimal(0):
        raise ValueError(f"ear must be >= 0, got {ear}")

    m = int(freq)
    e = float(ear)

    nominal = m * ((1.0 + e) ** (1.0 / m) - 1.0)
    return _quantize_rate(nominal)


def real_rate(
    nominal_rate: Decimal,
    inflation_rate: Decimal,
) -> Decimal:
    """Inflation-adjusted rate of return using the Fisher equation.

    r_real = (1 + r_nom) / (1 + π) − 1

    A 7% nominal return with 2.5% inflation gives ~4.39% real growth.

    Args:
        nominal_rate: Nominal rate as a decimal fraction. May be negative
                      (nominal loss).
        inflation_rate: Inflation rate as a decimal fraction. Must be > -1
                        (inflation of -100% causes division by zero).

    Returns:
        Real rate of return rounded to 6 decimal places.
    """
    if inflation_rate <= Decimal("-1"):
        raise ValueError(f"inflation_rate must be > -1, got {inflation_rate}")

    r = float(nominal_rate)
    pi = float(inflation_rate)

    real = (1.0 + r) / (1.0 + pi) - 1.0
    return _quantize_rate(real)


def cagr(
    pv: Decimal,
    fv: Decimal,
    years: int | float,
) -> Decimal:
    """Compound Annual Growth Rate.

    CAGR = (FV / PV)^(1/t) − 1

    "My portfolio went from €10K to €18K in 5 years — what was my
    annualized return?"

    Args:
        pv: Starting value. Must be > 0.
        fv: Ending value. Must be >= 0.
        years: Time period in years. Must be > 0.

    Returns:
        CAGR as a decimal fraction, rounded to 6 decimal places.
        Can be negative if value declined.
    """
    if pv <= Decimal(0):
        raise ValueError(f"pv must be > 0, got {pv}")
    if fv < Decimal(0):
        raise ValueError(f"fv must be >= 0, got {fv}")
    if years <= 0:
        raise ValueError(f"years must be > 0, got {years}")

    rate = (float(fv) / float(pv)) ** (1.0 / float(years)) - 1.0
    return _quantize_rate(rate)
