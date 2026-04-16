"""Tests for database schema initialisation and category seed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pytest

from munger_matics.categories import seed_categories
from munger_matics.database.schema import initialise

CATEGORIES_CONFIG = (
    Path(__file__).parent.parent.parent / "config" / "default_categories.toml"
)


def _scalar(row: tuple[Any, ...] | None) -> Any:
    """Unwrap the first column of a fetchone() result; fails the test if None."""
    assert row is not None
    return row[0]


@pytest.fixture
def db() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    initialise(conn)
    seed_categories(conn, CATEGORIES_CONFIG)
    return conn


# ---------------------------------------------------------------------------
# Table existence
# ---------------------------------------------------------------------------


def test_all_tables_created(db: duckdb.DuckDBPyConnection) -> None:
    tables = {row[0] for row in db.execute("SHOW TABLES").fetchall()}
    assert tables == {
        "accounts",
        "categories",
        "category_rules",
        "transactions",
        "budgets",
        "savings_goals",
    }


# ---------------------------------------------------------------------------
# accounts table
# ---------------------------------------------------------------------------


def test_accounts_type_check_rejects_invalid(db: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO accounts (name, type) VALUES ('Test', 'current_account')"
        )


def test_accounts_type_check_accepts_all_valid_types(
    db: duckdb.DuckDBPyConnection,
) -> None:
    valid_types = (
        "checking",
        "savings",
        "investment",
        "retirement",
        "credit_card",
        "loan",
    )
    for account_type in valid_types:
        db.execute(
            "INSERT INTO accounts (name, type) VALUES (?, ?)",
            [f"Account {account_type}", account_type],
        )
    count = _scalar(db.execute("SELECT COUNT(*) FROM accounts").fetchone())
    assert count == len(valid_types)


def test_accounts_opening_balance_defaults_to_zero(
    db: duckdb.DuckDBPyConnection,
) -> None:
    db.execute("INSERT INTO accounts (name, type) VALUES ('CCF', 'checking')")
    balance = _scalar(db.execute("SELECT opening_balance FROM accounts").fetchone())
    assert balance == 0


def test_accounts_currency_defaults_to_eur(db: duckdb.DuckDBPyConnection) -> None:
    db.execute("INSERT INTO accounts (name, type) VALUES ('CCF', 'checking')")
    currency = _scalar(db.execute("SELECT currency FROM accounts").fetchone())
    assert currency == "EUR"


def test_accounts_is_active_defaults_to_true(db: duckdb.DuckDBPyConnection) -> None:
    db.execute("INSERT INTO accounts (name, type) VALUES ('CCF', 'checking')")
    is_active = _scalar(db.execute("SELECT is_active FROM accounts").fetchone())
    assert is_active is True


# ---------------------------------------------------------------------------
# categories table
# ---------------------------------------------------------------------------


def test_categories_direction_check_rejects_invalid(
    db: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO categories (name, direction) VALUES ('Misc', 'unknown')"
        )


def test_categories_parent_id_self_fk(db: duckdb.DuckDBPyConnection) -> None:
    db.execute(
        "INSERT INTO categories (id, name, direction) VALUES ('parent-1', 'Food & Drink', 'expense')"
    )
    db.execute(
        "INSERT INTO categories (name, direction, parent_id) VALUES ('Organic Market', 'expense', 'parent-1')"
    )
    row = db.execute(
        "SELECT parent_id FROM categories WHERE name = 'Organic Market'"
    ).fetchone()
    assert row is not None
    assert row[0] == "parent-1"


def test_categories_parent_fk_rejects_nonexistent_parent(
    db: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO categories (name, direction, parent_id) VALUES ('Sub', 'expense', 'does-not-exist')"
        )


# ---------------------------------------------------------------------------
# transactions table — import_hash UNIQUE constraint
# ---------------------------------------------------------------------------


def _insert_account(conn: duckdb.DuckDBPyConnection, account_id: str) -> None:
    conn.execute(
        "INSERT INTO accounts (id, name, type) VALUES (?, 'CCF', 'checking')",
        [account_id],
    )


def test_transactions_import_hash_unique_constraint(
    db: duckdb.DuckDBPyConnection,
) -> None:
    _insert_account(db, "acct-1")
    db.execute(
        """
        INSERT INTO transactions (account_id, date, amount, description, import_hash)
        VALUES ('acct-1', '2026-03-01', -23.95, 'GRAND FRAIS', 'hash-abc')
        """
    )
    with pytest.raises(Exception):
        db.execute(
            """
            INSERT INTO transactions (account_id, date, amount, description, import_hash)
            VALUES ('acct-1', '2026-03-02', -10.00, 'OTHER SHOP', 'hash-abc')
            """
        )


def test_transactions_import_hash_null_allowed_multiple_times(
    db: duckdb.DuckDBPyConnection,
) -> None:
    # NULL import_hash is allowed for manually-entered transactions (no dedup needed)
    _insert_account(db, "acct-2")
    db.execute(
        """
        INSERT INTO transactions (account_id, date, amount, description, source, import_hash)
        VALUES ('acct-2', '2026-03-01', -10.00, 'Manual A', 'manual', NULL)
        """
    )
    db.execute(
        """
        INSERT INTO transactions (account_id, date, amount, description, source, import_hash)
        VALUES ('acct-2', '2026-03-02', -20.00, 'Manual B', 'manual', NULL)
        """
    )
    count = _scalar(
        db.execute(
            "SELECT COUNT(*) FROM transactions WHERE account_id = 'acct-2'"
        ).fetchone()
    )
    assert count == 2


def test_transactions_account_fk_rejects_unknown_account(
    db: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(Exception):
        db.execute(
            """
            INSERT INTO transactions (account_id, date, amount, description)
            VALUES ('no-such-account', '2026-03-01', -10.00, 'Test')
            """
        )


# ---------------------------------------------------------------------------
# budgets table — UNIQUE (category_id, month)
# ---------------------------------------------------------------------------


def test_budgets_unique_category_month(db: duckdb.DuckDBPyConnection) -> None:
    cat_id = _scalar(
        db.execute("SELECT id FROM categories WHERE name = 'Groceries'").fetchone()
    )
    db.execute(
        "INSERT INTO budgets (category_id, month, amount) VALUES (?, '2026-03-01', 400)",
        [cat_id],
    )
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO budgets (category_id, month, amount) VALUES (?, '2026-03-01', 500)",
            [cat_id],
        )


def test_budgets_different_months_allowed(db: duckdb.DuckDBPyConnection) -> None:
    cat_id = _scalar(
        db.execute("SELECT id FROM categories WHERE name = 'Groceries'").fetchone()
    )
    db.execute(
        "INSERT INTO budgets (category_id, month, amount) VALUES (?, '2026-02-01', 400)",
        [cat_id],
    )
    db.execute(
        "INSERT INTO budgets (category_id, month, amount) VALUES (?, '2026-03-01', 420)",
        [cat_id],
    )
    count = _scalar(
        db.execute(
            "SELECT COUNT(*) FROM budgets WHERE category_id = ?", [cat_id]
        ).fetchone()
    )
    assert count == 2


# ---------------------------------------------------------------------------
# Category seed
# ---------------------------------------------------------------------------


def test_seed_produces_correct_totals(db: duckdb.DuckDBPyConnection) -> None:
    rows = db.execute(
        "SELECT direction, COUNT(*) FROM categories GROUP BY direction"
    ).fetchall()
    counts = {direction: n for direction, n in rows}
    assert counts["income"] == 5
    assert counts["expense"] == 13
    assert counts["transfer"] == 2


def test_seed_all_default_categories_have_no_parent(
    db: duckdb.DuckDBPyConnection,
) -> None:
    rows = db.execute(
        "SELECT name FROM categories WHERE parent_id IS NOT NULL"
    ).fetchall()
    assert rows == [], f"Default categories should have no parent: {rows}"


def test_seed_is_idempotent(db: duckdb.DuckDBPyConnection) -> None:
    count_before = _scalar(db.execute("SELECT COUNT(*) FROM categories").fetchone())
    seed_categories(db, CATEGORIES_CONFIG)
    count_after = _scalar(db.execute("SELECT COUNT(*) FROM categories").fetchone())
    assert count_before == count_after


# ---------------------------------------------------------------------------
# category_rules table
# ---------------------------------------------------------------------------


def test_category_rules_match_type_check_rejects_invalid(
    db: duckdb.DuckDBPyConnection,
) -> None:
    cat_id = _scalar(
        db.execute("SELECT id FROM categories WHERE name = 'Groceries'").fetchone()
    )
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO category_rules (pattern, match_type, category_id) VALUES ('ALDI', 'fuzzy', ?)",
            [cat_id],
        )


def test_category_rules_match_type_accepts_all_valid(
    db: duckdb.DuckDBPyConnection,
) -> None:
    cat_id = _scalar(
        db.execute("SELECT id FROM categories WHERE name = 'Groceries'").fetchone()
    )
    for match_type in ("contains", "starts_with", "regex"):
        db.execute(
            "INSERT INTO category_rules (pattern, match_type, category_id) VALUES (?, ?, ?)",
            [f"pattern-{match_type}", match_type, cat_id],
        )
    count = _scalar(db.execute("SELECT COUNT(*) FROM category_rules").fetchone())
    assert count == 3
