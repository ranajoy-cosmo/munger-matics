from __future__ import annotations

import datetime
from decimal import Decimal

import duckdb
from pydantic import BaseModel, field_validator


class Budget(BaseModel):
    id: str
    category_id: str
    month: datetime.date
    amount: Decimal
    created_at: datetime.datetime

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: object) -> Decimal:
        return Decimal(str(v))


class BudgetVsActual(BaseModel):
    category_id: str
    category_name: str
    direction: str
    month: datetime.date
    budgeted: Decimal
    actual: Decimal
    variance: (
        Decimal  # actual - budgeted; positive = underspent (expenses) or missed income
    )
    pct_used: Decimal | None  # actual / budgeted; None if budgeted is zero

    @field_validator("budgeted", "actual", "variance", mode="before")
    @classmethod
    def coerce_decimal(cls, v: object) -> Decimal:
        return Decimal(str(v))


# ---------------------------------------------------------------------------
# Repository functions
# ---------------------------------------------------------------------------


def set_budget(
    conn: duckdb.DuckDBPyConnection,
    category_id: str,
    month: datetime.date,
    amount: Decimal,
) -> str:
    """Create or replace the budget for (category_id, month).

    If a budget already exists for this category and month it is updated
    in-place and the same ID returned.  Otherwise a new row is inserted.

    Sign convention matches transactions: negative amount = planned expense,
    positive = planned income.

    Returns:
        The UUID of the budget row.

    Raises:
        KeyError: if category_id does not exist.
    """
    cat_exists = conn.execute(
        "SELECT 1 FROM categories WHERE id = ?", [category_id]
    ).fetchone()
    if cat_exists is None:
        raise KeyError(f"Category not found: {category_id!r}")

    existing = conn.execute(
        "SELECT id FROM budgets WHERE category_id = ? AND month = ?",
        [category_id, month],
    ).fetchone()

    if existing is not None:
        conn.execute(
            "UPDATE budgets SET amount = ? WHERE id = ?",
            [str(amount), str(existing[0])],
        )
        return str(existing[0])

    row = conn.execute(
        "INSERT INTO budgets (category_id, month, amount) VALUES (?, ?, ?) RETURNING id",
        [category_id, month, str(amount)],
    ).fetchone()
    assert row is not None
    return str(row[0])


def list_budgets(
    conn: duckdb.DuckDBPyConnection,
    *,
    month: datetime.date | None = None,
) -> list[Budget]:
    """Return all budgets, optionally filtered to a specific month.

    Ordered by month ascending, then category sort_order.
    """
    if month is not None:
        rows = conn.execute(
            """
            SELECT b.id, b.category_id, b.month, b.amount, b.created_at
            FROM budgets b
            JOIN categories c ON c.id = b.category_id
            WHERE b.month = ?
            ORDER BY b.month, c.sort_order, c.name
            """,
            [month],
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT b.id, b.category_id, b.month, b.amount, b.created_at
            FROM budgets b
            JOIN categories c ON c.id = b.category_id
            ORDER BY b.month, c.sort_order, c.name
            """,
        ).fetchall()

    return [
        Budget(
            id=r[0],
            category_id=r[1],
            month=r[2],
            amount=r[3],
            created_at=r[4],
        )
        for r in rows
    ]


def get_budget_vs_actual(
    conn: duckdb.DuckDBPyConnection,
    month: datetime.date,
) -> list[BudgetVsActual]:
    """Return budgeted vs actual spending for every budgeted category in a month.

    Only categories that have a budget row for the given month are returned.
    Actual amounts come from transactions whose ``date`` falls in that calendar
    month, regardless of ``value_date``.

    ``variance = actual - budgeted``
        For expense categories (both values negative):
            positive variance → underspent (good)
            negative variance → overspent (bad)
        For income categories:
            positive variance → earned more than planned
            negative variance → missed income target

    ``pct_used = actual / budgeted``
        None when budgeted is zero.
    """
    # Use the first day of the month for the comparison
    month_start = datetime.date(month.year, month.month, 1)

    rows = conn.execute(
        """
        WITH actual AS (
            SELECT
                category_id,
                SUM(amount)::DECIMAL(15,2) AS total
            FROM transactions
            WHERE DATE_TRUNC('month', date)::DATE = ?
              AND category_id IS NOT NULL
            GROUP BY category_id
        )
        SELECT
            b.category_id,
            c.name                                   AS category_name,
            c.direction,
            b.month,
            b.amount::DECIMAL(15,2)                  AS budgeted,
            COALESCE(a.total, 0)::DECIMAL(15,2)      AS actual,
            (COALESCE(a.total, 0) - b.amount)::DECIMAL(15,2) AS variance,
            CASE
                WHEN b.amount = 0 THEN NULL
                ELSE (COALESCE(a.total, 0) / b.amount)::DECIMAL(15,4)
            END AS pct_used
        FROM budgets b
        JOIN categories c ON c.id = b.category_id
        LEFT JOIN actual a ON a.category_id = b.category_id
        WHERE b.month = ?
        ORDER BY c.direction, c.sort_order, c.name
        """,
        [month_start, month_start],
    ).fetchall()

    result: list[BudgetVsActual] = []
    for r in rows:
        pct_used = Decimal(str(r[7])) if r[7] is not None else None
        result.append(
            BudgetVsActual(
                category_id=r[0],
                category_name=r[1],
                direction=r[2],
                month=r[3],
                budgeted=r[4],
                actual=r[5],
                variance=r[6],
                pct_used=pct_used,
            )
        )
    return result
