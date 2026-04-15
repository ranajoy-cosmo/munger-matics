from __future__ import annotations

import datetime
from decimal import Decimal

import duckdb
from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class Transaction(BaseModel):
    id: str
    account_id: str
    date: datetime.date
    value_date: datetime.date | None
    amount: Decimal
    description: str
    category_id: str | None
    is_transfer: bool
    transfer_peer_id: str | None
    import_hash: str | None
    source: str
    created_at: datetime.datetime

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: object) -> Decimal:
        return Decimal(str(v))


class MonthlySummary(BaseModel):
    month: datetime.date
    account_id: str | None
    income: Decimal
    expenses: Decimal
    net: Decimal

    @field_validator("income", "expenses", "net", mode="before")
    @classmethod
    def coerce_decimal(cls, v: object) -> Decimal:
        return Decimal(str(v))


# ---------------------------------------------------------------------------
# Repository — queries
# ---------------------------------------------------------------------------

_SELECT_TRANSACTION = """
    SELECT
        id, account_id, date, value_date, amount, description,
        category_id, is_transfer, transfer_peer_id, import_hash, source, created_at
    FROM transactions
"""


def _row_to_transaction(row: tuple[object, ...]) -> Transaction:
    return Transaction(
        id=row[0],
        account_id=row[1],
        date=row[2],
        value_date=row[3],
        amount=row[4],
        description=row[5],
        category_id=row[6],
        is_transfer=row[7],
        transfer_peer_id=row[8],
        import_hash=row[9],
        source=row[10],
        created_at=row[11],
    )


def get_transaction(
    conn: duckdb.DuckDBPyConnection, transaction_id: str
) -> Transaction:
    """Return a Transaction by ID. Raises KeyError if not found."""
    row = conn.execute(
        _SELECT_TRANSACTION + " WHERE id = ?",
        [transaction_id],
    ).fetchone()
    if row is None:
        raise KeyError(f"Transaction not found: {transaction_id!r}")
    return _row_to_transaction(row)


def list_transactions(
    conn: duckdb.DuckDBPyConnection,
    *,
    account_id: str | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    category_id: str | None = None,
    search: str | None = None,
    uncategorised_only: bool = False,
    limit: int | None = None,
) -> list[Transaction]:
    """Return transactions matching the supplied filters, ordered date DESC.

    All filters are optional and can be combined freely.

    Args:
        account_id:          Restrict to a single account.
        date_from:           Include transactions on or after this date.
        date_to:             Include transactions on or before this date.
        category_id:         Restrict to transactions in this category.
        search:              Case-insensitive substring match on ``description``.
        uncategorised_only:  If True, return only rows where category_id IS NULL.
        limit:               Maximum number of rows to return.
    """
    clauses: list[str] = []
    params: list[object] = []

    if account_id is not None:
        clauses.append("account_id = ?")
        params.append(account_id)
    if date_from is not None:
        clauses.append("date >= ?")
        params.append(date_from)
    if date_to is not None:
        clauses.append("date <= ?")
        params.append(date_to)
    if category_id is not None:
        clauses.append("category_id = ?")
        params.append(category_id)
    if search is not None:
        clauses.append("lower(description) LIKE lower(?)")
        params.append(f"%{search}%")
    if uncategorised_only:
        clauses.append("category_id IS NULL")

    query = _SELECT_TRANSACTION
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY date DESC, created_at DESC"
    if limit is not None:
        query += f" LIMIT {int(limit)}"

    return [_row_to_transaction(r) for r in conn.execute(query, params).fetchall()]


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


def update_category(
    conn: duckdb.DuckDBPyConnection,
    transaction_id: str,
    category_id: str | None,
) -> None:
    """Set (or clear) the category on a transaction.

    Raises KeyError if the transaction does not exist.
    Raises KeyError if category_id is provided but the category does not exist.
    """
    exists = conn.execute(
        "SELECT 1 FROM transactions WHERE id = ?", [transaction_id]
    ).fetchone()
    if exists is None:
        raise KeyError(f"Transaction not found: {transaction_id!r}")

    if category_id is not None:
        cat_exists = conn.execute(
            "SELECT 1 FROM categories WHERE id = ?", [category_id]
        ).fetchone()
        if cat_exists is None:
            raise KeyError(f"Category not found: {category_id!r}")

    conn.execute(
        "UPDATE transactions SET category_id = ? WHERE id = ?",
        [category_id, transaction_id],
    )


def mark_transfer(
    conn: duckdb.DuckDBPyConnection,
    transaction_id_a: str,
    transaction_id_b: str,
) -> None:
    """Link two transactions as a transfer pair.

    Sets ``is_transfer = true`` and ``transfer_peer_id`` on both rows.
    Raises KeyError if either transaction is not found.
    """
    for tid in (transaction_id_a, transaction_id_b):
        if (
            conn.execute("SELECT 1 FROM transactions WHERE id = ?", [tid]).fetchone()
            is None
        ):
            raise KeyError(f"Transaction not found: {tid!r}")

    # Use a single UPDATE statement to avoid DuckDB's self-FK constraint error
    # that occurs when updating two rows that reference each other sequentially.
    conn.execute(
        """
        UPDATE transactions
        SET is_transfer = true,
            transfer_peer_id = CASE WHEN id = ? THEN ? WHEN id = ? THEN ? END
        WHERE id IN (?, ?)
        """,
        [
            transaction_id_a,
            transaction_id_b,
            transaction_id_b,
            transaction_id_a,
            transaction_id_a,
            transaction_id_b,
        ],
    )


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------


def get_monthly_summary(
    conn: duckdb.DuckDBPyConnection,
    *,
    account_id: str | None = None,
) -> list[MonthlySummary]:
    """Return income, expenses, and net per calendar month.

    Months are represented as the first day of the month
    (DATE_TRUNC('month', date)).  Results are ordered chronologically.

    Sign convention (same as the transactions table):
        ``income``   — sum of positive amounts (money in), always >= 0
        ``expenses`` — sum of negative amounts (money out), always <= 0
        ``net``      — total sum (income + expenses)

    Args:
        account_id: If supplied, restrict to a single account.
    """
    if account_id is not None:
        # Two params: one for the literal in SELECT, one for the WHERE filter.
        rows = conn.execute(
            """
            SELECT
                DATE_TRUNC('month', date)::DATE                               AS month,
                ? AS account_id,
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), 0) AS expenses,
                COALESCE(SUM(amount), 0)                                       AS net
            FROM transactions
            WHERE account_id = ?
            GROUP BY DATE_TRUNC('month', date)
            ORDER BY month
            """,
            [account_id, account_id],
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT
                DATE_TRUNC('month', date)::DATE                               AS month,
                NULL AS account_id,
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), 0) AS expenses,
                COALESCE(SUM(amount), 0)                                       AS net
            FROM transactions
            GROUP BY DATE_TRUNC('month', date)
            ORDER BY month
            """,
        ).fetchall()

    return [
        MonthlySummary(
            month=r[0],
            account_id=r[1],
            income=r[2],
            expenses=r[3],
            net=r[4],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Category breakdown
# ---------------------------------------------------------------------------


class CategoryBreakdown(BaseModel):
    month: datetime.date
    category_id: str | None
    category_name: str | None
    direction: str | None  # 'income' | 'expense' | 'transfer' | None (uncategorised)
    amount: Decimal

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: object) -> Decimal:
        return Decimal(str(v))


def get_category_breakdown(
    conn: duckdb.DuckDBPyConnection,
    *,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    account_id: str | None = None,
) -> list[CategoryBreakdown]:
    """Return total transaction amounts grouped by (month, category).

    One row per (calendar month, category). Uncategorised transactions appear
    as a row with ``category_id=None``, ``category_name=None``,
    ``direction=None``.

    Sign convention (same as the rest of the codebase):
        positive amount — money in
        negative amount — money out

    Args:
        date_from:  Include transactions on or after this date.
        date_to:    Include transactions on or before this date.
        account_id: Restrict to a single account.
    """
    clauses: list[str] = []
    params: list[object] = []

    if account_id is not None:
        clauses.append("t.account_id = ?")
        params.append(account_id)
    if date_from is not None:
        clauses.append("t.date >= ?")
        params.append(date_from)
    if date_to is not None:
        clauses.append("t.date <= ?")
        params.append(date_to)

    where_clause = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    rows = conn.execute(
        f"""
        SELECT
            DATE_TRUNC('month', t.date)::DATE AS month,
            t.category_id,
            c.name                            AS category_name,
            c.direction,
            SUM(t.amount)::DECIMAL(15,2)      AS amount
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        {where_clause}
        GROUP BY DATE_TRUNC('month', t.date), t.category_id, c.name, c.direction
        ORDER BY month, c.direction NULLS LAST, c.name NULLS LAST
        """,
        params,
    ).fetchall()

    return [
        CategoryBreakdown(
            month=r[0],
            category_id=r[1],
            category_name=r[2],
            direction=r[3],
            amount=r[4],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Derived metrics
# ---------------------------------------------------------------------------


class SavingsRatePoint(BaseModel):
    month: datetime.date
    income: Decimal
    net: Decimal
    # None when income is zero — savings rate is undefined
    savings_rate: Decimal | None

    @field_validator("income", "net", mode="before")
    @classmethod
    def coerce_decimal(cls, v: object) -> Decimal:
        return Decimal(str(v))


def get_savings_rate_history(
    conn: duckdb.DuckDBPyConnection,
    *,
    account_id: str | None = None,
) -> list[SavingsRatePoint]:
    """Return month-by-month income, net, and savings rate.

    Savings rate = net / income.  None when there is no income in a month
    (division by zero is undefined, not zero).

    Args:
        account_id: If supplied, restrict to a single account.
    """
    if account_id is not None:
        rows = conn.execute(
            """
            SELECT
                DATE_TRUNC('month', date)::DATE                               AS month,
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(amount), 0)                                       AS net
            FROM transactions
            WHERE account_id = ?
            GROUP BY DATE_TRUNC('month', date)
            ORDER BY month
            """,
            [account_id],
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT
                DATE_TRUNC('month', date)::DATE                               AS month,
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(amount), 0)                                       AS net
            FROM transactions
            GROUP BY DATE_TRUNC('month', date)
            ORDER BY month
            """,
        ).fetchall()

    result: list[SavingsRatePoint] = []
    for r in rows:
        income = Decimal(str(r[1]))
        net = Decimal(str(r[2]))
        savings_rate = (
            (net / income).quantize(Decimal("0.0001"))
            if income > Decimal("0")
            else None
        )
        result.append(
            SavingsRatePoint(
                month=r[0], income=income, net=net, savings_rate=savings_rate
            )
        )
    return result


def get_spending_runway(
    conn: duckdb.DuckDBPyConnection,
    account_id: str,
    *,
    lookback_months: int = 3,
) -> Decimal:
    """Return estimated months of spending remaining at the current rate.

    runway = current_balance / |avg_monthly_expenses|

    The average is taken over calendar months within the lookback window that
    have at least one debit transaction.  Months with zero spending are excluded
    from the average so that months with no data don't artificially inflate
    the runway.

    Args:
        account_id:      The account to analyse.
        lookback_months: How many months back from the most recent transaction
                         to include in the expense average.  Defaults to 3.

    Returns:
        Runway in months, rounded to two decimal places.

    Raises:
        KeyError:   if the account does not exist.
        ValueError: if there are no transactions, or no spending within the
                    lookback window.
    """
    exists = conn.execute(
        "SELECT opening_balance FROM accounts WHERE id = ?", [account_id]
    ).fetchone()
    if exists is None:
        raise KeyError(f"Account not found: {account_id!r}")

    balance_row = conn.execute(
        """
        SELECT a.opening_balance + COALESCE(SUM(t.amount), 0)
        FROM accounts a
        LEFT JOIN transactions t ON t.account_id = a.id
        WHERE a.id = ?
        GROUP BY a.opening_balance
        """,
        [account_id],
    ).fetchone()
    current_balance = Decimal(str(balance_row[0]))  # type: ignore[index]

    max_date_row = conn.execute(
        "SELECT MAX(date) FROM transactions WHERE account_id = ?", [account_id]
    ).fetchone()
    if max_date_row is None or max_date_row[0] is None:
        raise ValueError(f"No transactions for account: {account_id!r}")

    last_date: datetime.date = max_date_row[0]
    # First day of the month lookback_months before last_date (inclusive boundary)
    total = last_date.year * 12 + last_date.month - lookback_months
    lookback_start = datetime.date(total // 12, total % 12 + 1, 1)

    expense_rows = conn.execute(
        """
        SELECT
            DATE_TRUNC('month', date)::DATE AS month,
            SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) AS expenses
        FROM transactions
        WHERE account_id = ?
          AND date >= ?
        GROUP BY DATE_TRUNC('month', date)
        HAVING SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) < 0
        ORDER BY month
        """,
        [account_id, lookback_start],
    ).fetchall()

    if not expense_rows:
        raise ValueError(
            f"No expense data in the last {lookback_months} months for account: {account_id!r}"
        )

    total_expenses = sum(Decimal(str(r[1])) for r in expense_rows)
    avg_monthly_expenses = Decimal(str(total_expenses)) / len(expense_rows)
    # avg_monthly_expenses is negative; take abs before dividing
    return (current_balance / abs(avg_monthly_expenses)).quantize(Decimal("0.01"))
