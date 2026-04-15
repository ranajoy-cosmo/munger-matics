from __future__ import annotations

import datetime
from decimal import Decimal

import duckdb
from pydantic import BaseModel, field_validator

from munger_matics.accounts.repository import get_balance
from munger_matics.finance import (
    CompoundingFreq,
    fv_annuity,
    future_value_compound,
)


class SavingsGoal(BaseModel):
    id: str
    name: str
    target_amount: Decimal
    target_date: datetime.date | None
    created_at: datetime.datetime

    @field_validator("target_amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: object) -> Decimal:
        return Decimal(str(v))


class GoalProgress(BaseModel):
    goal: SavingsGoal
    account_id: str
    current_balance: Decimal
    projected_balance: Decimal
    on_track: bool
    months_remaining: int | None

    @field_validator("current_balance", "projected_balance", mode="before")
    @classmethod
    def coerce_decimal(cls, v: object) -> Decimal:
        return Decimal(str(v))


# ---------------------------------------------------------------------------
# Repository functions
# ---------------------------------------------------------------------------


def add_goal(
    conn: duckdb.DuckDBPyConnection,
    name: str,
    target_amount: Decimal,
    target_date: datetime.date | None = None,
) -> str:
    """Insert a new savings goal and return its UUID.

    Args:
        name:          Human-readable label for the goal.
        target_amount: The balance to reach.  Must be > 0.
        target_date:   Optional deadline.  None means open-ended.

    Raises:
        ValueError: if target_amount is not positive.
    """
    if target_amount <= Decimal("0"):
        raise ValueError(f"target_amount must be > 0, got {target_amount}")

    row = conn.execute(
        """
        INSERT INTO savings_goals (name, target_amount, target_date)
        VALUES (?, ?, ?)
        RETURNING id
        """,
        [name, str(target_amount), target_date],
    ).fetchone()
    assert row is not None
    return str(row[0])


def list_goals(conn: duckdb.DuckDBPyConnection) -> list[SavingsGoal]:
    """Return all savings goals ordered by target_date (NULLs last), then name."""
    rows = conn.execute(
        """
        SELECT id, name, target_amount, target_date, created_at
        FROM savings_goals
        ORDER BY target_date NULLS LAST, name
        """
    ).fetchall()

    return [
        SavingsGoal(
            id=r[0],
            name=r[1],
            target_amount=r[2],
            target_date=r[3],
            created_at=r[4],
        )
        for r in rows
    ]


def get_goal_progress(
    conn: duckdb.DuckDBPyConnection,
    goal_id: str,
    account_id: str,
    *,
    monthly_contribution: Decimal,
    annual_rate: Decimal,
    as_of: datetime.date | None = None,
) -> GoalProgress:
    """Compute current and projected progress toward a savings goal.

    The projection formula combines:
        - the current balance compounding to target_date
          (``future_value_compound``)
        - ongoing monthly contributions growing to target_date
          (``fv_annuity``)

    Both use ``CompoundingFreq.MONTHLY``.

    When ``target_date`` is None the goal is open-ended; ``projected_balance``
    equals ``current_balance`` and ``months_remaining`` is None.
    When the target date is already passed (months_remaining <= 0),
    ``projected_balance`` equals ``current_balance``.
    When ``current_balance`` is negative the projection assumes zero growth
    on the existing balance (you cannot compound a debt in a savings model).

    Args:
        goal_id:              UUID of the savings goal.
        account_id:           Account whose balance is used as the starting point.
        monthly_contribution: Monthly savings contribution.  Must be >= 0.
        annual_rate:          Expected annual growth rate as a decimal fraction.
        as_of:                Reference date for "today".  Defaults to
                              ``datetime.date.today()``.

    Raises:
        KeyError:   if goal_id or account_id does not exist.
        ValueError: if monthly_contribution < 0.
    """
    if monthly_contribution < Decimal("0"):
        raise ValueError(
            f"monthly_contribution must be >= 0, got {monthly_contribution}"
        )

    if as_of is None:
        as_of = datetime.date.today()

    row = conn.execute(
        "SELECT id, name, target_amount, target_date, created_at FROM savings_goals WHERE id = ?",
        [goal_id],
    ).fetchone()
    if row is None:
        raise KeyError(f"Savings goal not found: {goal_id!r}")

    goal = SavingsGoal(
        id=row[0],
        name=row[1],
        target_amount=row[2],
        target_date=row[3],
        created_at=row[4],
    )

    # get_balance raises KeyError if account not found
    current_balance = get_balance(conn, account_id)

    months_remaining: int | None
    projected_balance: Decimal

    if goal.target_date is None:
        months_remaining = None
        projected_balance = current_balance
    else:
        months_remaining = (goal.target_date.year - as_of.year) * 12 + (
            goal.target_date.month - as_of.month
        )

        if months_remaining <= 0 or current_balance < Decimal("0"):
            projected_balance = current_balance
        else:
            years = float(months_remaining) / 12.0
            fv_existing = future_value_compound(
                max(current_balance, Decimal("0")),
                annual_rate,
                years,
                CompoundingFreq.MONTHLY,
            )
            fv_contributions = fv_annuity(
                monthly_contribution,
                annual_rate,
                years,
                CompoundingFreq.MONTHLY,
            )
            projected_balance = fv_existing + fv_contributions

    on_track = projected_balance >= goal.target_amount

    return GoalProgress(
        goal=goal,
        account_id=account_id,
        current_balance=current_balance,
        projected_balance=projected_balance,
        on_track=on_track,
        months_remaining=months_remaining,
    )
