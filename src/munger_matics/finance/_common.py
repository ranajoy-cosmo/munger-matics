from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from enum import IntEnum


class CompoundingFreq(IntEnum):
    """Number of compounding periods per year."""

    ANNUAL = 1
    SEMI_ANNUAL = 2
    QUARTERLY = 4
    MONTHLY = 12
    DAILY = 365


_CENT = Decimal("0.01")
_RATE_PRECISION = Decimal("0.000001")


def _quantize(value: float) -> Decimal:
    """Round a float to the nearest cent (2 decimal places, ROUND_HALF_UP).

    Precision note: fractional exponentiation is computed via float (Python's
    Decimal does not support non-integer powers). The result is rounded to the
    nearest cent using ROUND_HALF_UP at the point of return. Intermediate
    rounding is deliberately avoided; only the final output is rounded.
    """
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


def _quantize_rate(value: float) -> Decimal:
    """Round a float to 6 decimal places (rate precision, ROUND_HALF_UP)."""
    return Decimal(str(value)).quantize(_RATE_PRECISION, rounding=ROUND_HALF_UP)
