"""Tests for the accounts repository."""

from __future__ import annotations

from decimal import Decimal

import duckdb
import pytest

from munger_matics.accounts.repository import (
    Account,
    AccountType,
    add_account,
    deactivate_account,
    get_account,
    get_balance,
    list_accounts,
)
from munger_matics.database.schema import initialise


@pytest.fixture
def db() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    initialise(conn)
    return conn


# ---------------------------------------------------------------------------
# add_account
# ---------------------------------------------------------------------------


def test_add_account_returns_uuid(db: duckdb.DuckDBPyConnection) -> None:
    account_id = add_account(db, "CCF Chèques", AccountType.CHECKING)
    assert isinstance(account_id, str)
    assert len(account_id) == 36  # UUID format


def test_add_account_stored_correctly(db: duckdb.DuckDBPyConnection) -> None:
    account_id = add_account(
        db,
        name="Livret A",
        type=AccountType.SAVINGS,
        currency="EUR",
        opening_balance=Decimal("1000.00"),
    )
    account = get_account(db, account_id)
    assert account.name == "Livret A"
    assert account.type == AccountType.SAVINGS
    assert account.currency == "EUR"
    assert account.opening_balance == Decimal("1000.00")
    assert account.is_active is True


def test_add_account_defaults(db: duckdb.DuckDBPyConnection) -> None:
    account_id = add_account(db, "Test", AccountType.CHECKING)
    account = get_account(db, account_id)
    assert account.currency == "EUR"
    assert account.opening_balance == Decimal("0")
    assert account.is_active is True


def test_add_account_accepts_string_type(db: duckdb.DuckDBPyConnection) -> None:
    # The type parameter accepts plain strings matching the enum values
    account_id = add_account(db, "Invest", "investment")
    account = get_account(db, account_id)
    assert account.type == AccountType.INVESTMENT


# ---------------------------------------------------------------------------
# get_account
# ---------------------------------------------------------------------------


def test_get_account_raises_for_unknown_id(db: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(KeyError, match="no-such-id"):
        get_account(db, "no-such-id")


def test_get_account_returns_account_model(db: duckdb.DuckDBPyConnection) -> None:
    account_id = add_account(db, "CCF", AccountType.CHECKING)
    account = get_account(db, account_id)
    assert isinstance(account, Account)
    assert account.id == account_id


# ---------------------------------------------------------------------------
# list_accounts
# ---------------------------------------------------------------------------


def test_list_accounts_returns_active_by_default(db: duckdb.DuckDBPyConnection) -> None:
    id_a = add_account(db, "Active", AccountType.CHECKING)
    id_b = add_account(db, "Inactive", AccountType.SAVINGS)
    deactivate_account(db, id_b)

    accounts = list_accounts(db)
    ids = [a.id for a in accounts]
    assert id_a in ids
    assert id_b not in ids


def test_list_accounts_active_only_false_returns_all(
    db: duckdb.DuckDBPyConnection,
) -> None:
    id_a = add_account(db, "Active", AccountType.CHECKING)
    id_b = add_account(db, "Inactive", AccountType.SAVINGS)
    deactivate_account(db, id_b)

    accounts = list_accounts(db, active_only=False)
    ids = [a.id for a in accounts]
    assert id_a in ids
    assert id_b in ids


def test_list_accounts_empty_when_none(db: duckdb.DuckDBPyConnection) -> None:
    assert list_accounts(db) == []


def test_list_accounts_returns_account_models(db: duckdb.DuckDBPyConnection) -> None:
    add_account(db, "CCF", AccountType.CHECKING)
    accounts = list_accounts(db)
    assert all(isinstance(a, Account) for a in accounts)


# ---------------------------------------------------------------------------
# deactivate_account
# ---------------------------------------------------------------------------


def test_deactivate_account_sets_is_active_false(db: duckdb.DuckDBPyConnection) -> None:
    account_id = add_account(db, "CCF", AccountType.CHECKING)
    deactivate_account(db, account_id)
    account = get_account(db, account_id)
    assert account.is_active is False


def test_deactivate_account_raises_for_unknown_id(
    db: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(KeyError, match="no-such-id"):
        deactivate_account(db, "no-such-id")


def test_deactivate_account_is_idempotent(db: duckdb.DuckDBPyConnection) -> None:
    account_id = add_account(db, "CCF", AccountType.CHECKING)
    deactivate_account(db, account_id)
    # Second call should not raise even though already inactive
    deactivate_account(db, account_id)
    account = get_account(db, account_id)
    assert account.is_active is False


# ---------------------------------------------------------------------------
# get_balance
# ---------------------------------------------------------------------------


def test_get_balance_no_transactions_returns_opening_balance(
    db: duckdb.DuckDBPyConnection,
) -> None:
    account_id = add_account(
        db, "Livret A", AccountType.SAVINGS, opening_balance=Decimal("2500.00")
    )
    balance = get_balance(db, account_id)
    assert balance == Decimal("2500.00")


def test_get_balance_with_transactions(db: duckdb.DuckDBPyConnection) -> None:
    # opening = 1000, +500 credit, -200 debit → expected 1300
    account_id = add_account(
        db, "CCF", AccountType.CHECKING, opening_balance=Decimal("1000.00")
    )
    db.execute(
        """
        INSERT INTO transactions (account_id, date, amount, description)
        VALUES (?, '2026-03-01', 500.00, 'Salary'),
               (?, '2026-03-10', -200.00, 'Rent')
        """,
        [account_id, account_id],
    )
    balance = get_balance(db, account_id)
    assert balance == Decimal("1300.00")


def test_get_balance_zero_opening_balance(db: duckdb.DuckDBPyConnection) -> None:
    account_id = add_account(db, "CCF", AccountType.CHECKING)
    db.execute(
        "INSERT INTO transactions (account_id, date, amount, description) VALUES (?, '2026-03-01', -50.00, 'Shop')",
        [account_id],
    )
    balance = get_balance(db, account_id)
    assert balance == Decimal("-50.00")


def test_get_balance_raises_for_unknown_id(db: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(KeyError, match="no-such-id"):
        get_balance(db, "no-such-id")


def test_get_balance_decimal_precision(db: duckdb.DuckDBPyConnection) -> None:
    # Verify no float rounding: 0.10 + 0.20 must equal 0.30 exactly
    account_id = add_account(db, "CCF", AccountType.CHECKING)
    db.execute(
        """
        INSERT INTO transactions (account_id, date, amount, description)
        VALUES (?, '2026-03-01', 0.10, 'A'),
               (?, '2026-03-02', 0.20, 'B')
        """,
        [account_id, account_id],
    )
    balance = get_balance(db, account_id)
    assert balance == Decimal("0.30")


# ---------------------------------------------------------------------------
# Account Pydantic model
# ---------------------------------------------------------------------------


def test_account_model_coerces_opening_balance_to_decimal(
    db: duckdb.DuckDBPyConnection,
) -> None:
    account_id = add_account(
        db, "Test", AccountType.CHECKING, opening_balance=Decimal("123.45")
    )
    account = get_account(db, account_id)
    assert isinstance(account.opening_balance, Decimal)
    assert account.opening_balance == Decimal("123.45")
