from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

import duckdb
from pydantic import BaseModel, field_validator


class AccountType(StrEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    INVESTMENT = "investment"
    RETIREMENT = "retirement"
    CREDIT_CARD = "credit_card"
    LOAN = "loan"


class Account(BaseModel):
    id: str
    name: str
    type: AccountType
    currency: str
    opening_balance: Decimal
    is_active: bool
    created_at: datetime

    @field_validator("opening_balance", mode="before")
    @classmethod
    def coerce_to_decimal(cls, v: object) -> Decimal:
        return Decimal(str(v))


# ---------------------------------------------------------------------------
# Repository functions
# ---------------------------------------------------------------------------


def add_account(
    conn: duckdb.DuckDBPyConnection,
    name: str,
    type: AccountType
    | Literal["checking", "savings", "investment", "retirement", "credit_card", "loan"],
    currency: str = "EUR",
    opening_balance: Decimal = Decimal("0"),
) -> str:
    """Insert a new account and return its generated UUID."""
    row = conn.execute(
        """
        INSERT INTO accounts (name, type, currency, opening_balance)
        VALUES (?, ?, ?, ?)
        RETURNING id
        """,
        [name, str(type), currency, str(opening_balance)],
    ).fetchone()
    assert row is not None
    return str(row[0])


def get_account(conn: duckdb.DuckDBPyConnection, account_id: str) -> Account:
    """Return an Account by ID. Raises KeyError if not found."""
    row = conn.execute(
        """
        SELECT id, name, type, currency, opening_balance, is_active, created_at
        FROM accounts
        WHERE id = ?
        """,
        [account_id],
    ).fetchone()
    if row is None:
        raise KeyError(f"Account not found: {account_id!r}")
    return Account(
        id=row[0],
        name=row[1],
        type=row[2],
        currency=row[3],
        opening_balance=row[4],
        is_active=row[5],
        created_at=row[6],
    )


def list_accounts(
    conn: duckdb.DuckDBPyConnection,
    *,
    active_only: bool = True,
) -> list[Account]:
    """Return all accounts, optionally filtered to active ones only."""
    query = """
        SELECT id, name, type, currency, opening_balance, is_active, created_at
        FROM accounts
    """
    if active_only:
        query += " WHERE is_active = true"
    query += " ORDER BY created_at"

    rows = conn.execute(query).fetchall()
    return [
        Account(
            id=r[0],
            name=r[1],
            type=r[2],
            currency=r[3],
            opening_balance=r[4],
            is_active=r[5],
            created_at=r[6],
        )
        for r in rows
    ]


def deactivate_account(conn: duckdb.DuckDBPyConnection, account_id: str) -> None:
    """Soft-delete an account by setting is_active = false.

    Raises KeyError if the account does not exist.
    Idempotent: calling again on an already-inactive account is safe.
    """
    exists = conn.execute(
        "SELECT 1 FROM accounts WHERE id = ?", [account_id]
    ).fetchone()
    if exists is None:
        raise KeyError(f"Account not found: {account_id!r}")
    conn.execute(
        "UPDATE accounts SET is_active = false WHERE id = ?",
        [account_id],
    )


def get_balance(conn: duckdb.DuckDBPyConnection, account_id: str) -> Decimal:
    """Return the current balance: opening_balance + SUM(transaction amounts).

    Balance is never stored — computed fresh each call so it always reflects
    the current state of the transactions table.

    Raises KeyError if the account does not exist.
    """
    row = conn.execute(
        """
        SELECT
            a.opening_balance + COALESCE(SUM(t.amount), 0)
        FROM accounts a
        LEFT JOIN transactions t ON t.account_id = a.id
        WHERE a.id = ?
        GROUP BY a.opening_balance
        """,
        [account_id],
    ).fetchone()
    if row is None:
        raise KeyError(f"Account not found: {account_id!r}")
    return Decimal(str(row[0]))


# ---------------------------------------------------------------------------
# Balance history
# ---------------------------------------------------------------------------


class BalancePoint(BaseModel):
    month: date
    account_id: str
    balance: Decimal

    @field_validator("balance", mode="before")
    @classmethod
    def coerce_balance(cls, v: object) -> Decimal:
        return Decimal(str(v))


class NetWorthPoint(BaseModel):
    month: date
    assets: Decimal
    liabilities: Decimal
    net_worth: Decimal

    @field_validator("assets", "liabilities", "net_worth", mode="before")
    @classmethod
    def coerce_decimal(cls, v: object) -> Decimal:
        return Decimal(str(v))


def balance_history(
    conn: duckdb.DuckDBPyConnection,
    account_id: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[BalancePoint]:
    """Return month-end running balance for an account, one point per month
    where at least one transaction occurred.

    The balance at each point is: opening_balance + cumulative sum of all
    transaction amounts up to and including that month.

    Args:
        account_id: The account to query.
        date_from:  If supplied, exclude months before this date.
        date_to:    If supplied, exclude months after this date.

    Raises:
        KeyError: if the account does not exist.
    """
    opening_row = conn.execute(
        "SELECT opening_balance FROM accounts WHERE id = ?", [account_id]
    ).fetchone()
    if opening_row is None:
        raise KeyError(f"Account not found: {account_id!r}")
    opening_balance = Decimal(str(opening_row[0]))

    filter_clauses: list[str] = []
    params: list[object] = [account_id, opening_balance]

    if date_from is not None:
        filter_clauses.append("month >= ?")
        params.append(date_from)
    if date_to is not None:
        filter_clauses.append("month <= ?")
        params.append(date_to)

    where_clause = ""
    if filter_clauses:
        where_clause = "WHERE " + " AND ".join(filter_clauses)

    rows = conn.execute(
        f"""
        WITH monthly AS (
            SELECT
                DATE_TRUNC('month', date)::DATE AS month,
                SUM(amount) AS net_flow
            FROM transactions
            WHERE account_id = ?
            GROUP BY DATE_TRUNC('month', date)
        ),
        cumulative AS (
            SELECT
                month,
                ? + SUM(net_flow) OVER (ORDER BY month ROWS UNBOUNDED PRECEDING)
                    AS balance
            FROM monthly
        )
        SELECT month, balance
        FROM cumulative
        {where_clause}
        ORDER BY month
        """,
        params,
    ).fetchall()

    return [BalancePoint(month=r[0], account_id=account_id, balance=r[1]) for r in rows]


def net_worth_history(conn: duckdb.DuckDBPyConnection) -> list[NetWorthPoint]:
    """Return month-end net worth across all accounts, one point per calendar
    month in which any transaction was recorded.

    For months where an account has no transactions its balance is carried
    forward from the previous month (via a cross-joined cumulative window),
    so every account contributes to every month in the series.

    Columns:
        assets      — sum of balances for checking / savings / investment /
                      retirement accounts.
        liabilities — sum of balances for credit_card / loan accounts.
        net_worth   — assets + liabilities  (liabilities are typically negative,
                      so this equals assets minus absolute debt).
    """
    rows = conn.execute(
        """
        WITH all_months AS (
            SELECT DISTINCT DATE_TRUNC('month', date)::DATE AS month
            FROM transactions
        ),
        monthly_flows AS (
            SELECT
                account_id,
                DATE_TRUNC('month', date)::DATE AS month,
                SUM(amount) AS net_flow
            FROM transactions
            GROUP BY account_id, DATE_TRUNC('month', date)
        ),
        account_months AS (
            SELECT a.id AS account_id, a.type, a.opening_balance, m.month
            FROM accounts a
            CROSS JOIN all_months m
        ),
        account_flows AS (
            SELECT
                am.account_id,
                am.type,
                am.opening_balance,
                am.month,
                COALESCE(mf.net_flow, 0) AS net_flow
            FROM account_months am
            LEFT JOIN monthly_flows mf
                ON mf.account_id = am.account_id AND mf.month = am.month
        ),
        account_cumulative AS (
            SELECT
                account_id,
                type,
                month,
                opening_balance
                    + SUM(net_flow) OVER (
                        PARTITION BY account_id
                        ORDER BY month
                        ROWS UNBOUNDED PRECEDING
                    ) AS balance
            FROM account_flows
        )
        SELECT
            month,
            SUM(CASE
                WHEN type IN ('checking', 'savings', 'investment', 'retirement')
                THEN balance ELSE 0
            END)::DECIMAL(15,2) AS assets,
            SUM(CASE
                WHEN type IN ('credit_card', 'loan')
                THEN balance ELSE 0
            END)::DECIMAL(15,2) AS liabilities,
            SUM(balance)::DECIMAL(15,2) AS net_worth
        FROM account_cumulative
        GROUP BY month
        ORDER BY month
        """
    ).fetchall()

    return [
        NetWorthPoint(month=r[0], assets=r[1], liabilities=r[2], net_worth=r[3])
        for r in rows
    ]
