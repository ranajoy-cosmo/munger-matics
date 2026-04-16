"""Tests for the budget repository (Phase 11)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Generator

import duckdb
import pytest

from munger_matics.accounts import AccountType, add_account
from munger_matics.budgets import (
    Budget,
    BudgetVsActual,
    get_budget_vs_actual,
    list_budgets,
    set_budget,
)
from munger_matics.categories import seed_categories
from munger_matics.database.schema import initialise
from munger_matics.transactions import (
    insert_transactions,
    load_mapping,
    parse_csv,
    update_category,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
CCF_FIXTURE = FIXTURES / "sample_ccf.csv"
TOML_CONFIG = Path(__file__).parent.parent.parent / "config" / "csv_mappings.toml"
CATEGORIES_CONFIG = (
    Path(__file__).parent.parent.parent / "config" / "default_categories.toml"
)

MAR = date(2026, 3, 1)
FEB = date(2026, 2, 1)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    c = duckdb.connect(":memory:")
    initialise(c)
    seed_categories(c, CATEGORIES_CONFIG)
    yield c
    c.close()


@pytest.fixture
def ccf_id(conn: duckdb.DuckDBPyConnection) -> str:
    return add_account(conn, "CCF Chèques", AccountType.CHECKING)


@pytest.fixture
def ccf_populated(
    conn: duckdb.DuckDBPyConnection, ccf_id: str
) -> duckdb.DuckDBPyConnection:
    insert_transactions(
        conn, parse_csv(CCF_FIXTURE, ccf_id, load_mapping("ccf_checking", TOML_CONFIG))
    )
    return conn


def _cat_id(conn: duckdb.DuckDBPyConnection, name: str) -> str:
    row = conn.execute("SELECT id FROM categories WHERE name = ?", [name]).fetchone()
    assert row is not None
    return str(row[0])


# ---------------------------------------------------------------------------
# set_budget
# ---------------------------------------------------------------------------


def test_set_budget_returns_uuid(conn: duckdb.DuckDBPyConnection) -> None:
    salary_id = _cat_id(conn, "Salary")
    budget_id = set_budget(conn, salary_id, MAR, Decimal("3000.00"))
    assert isinstance(budget_id, str)
    assert len(budget_id) == 36


def test_set_budget_stores_values_correctly(conn: duckdb.DuckDBPyConnection) -> None:
    salary_id = _cat_id(conn, "Salary")
    budget_id = set_budget(conn, salary_id, MAR, Decimal("3000.00"))

    budgets = list_budgets(conn, month=MAR)
    assert len(budgets) == 1
    b = budgets[0]
    assert b.id == budget_id
    assert b.category_id == salary_id
    assert b.month == MAR
    assert b.amount == Decimal("3000.00")


def test_set_budget_upserts_on_same_month(conn: duckdb.DuckDBPyConnection) -> None:
    salary_id = _cat_id(conn, "Salary")
    id1 = set_budget(conn, salary_id, MAR, Decimal("3000.00"))
    id2 = set_budget(conn, salary_id, MAR, Decimal("3200.00"))

    # Same row updated — same ID returned
    assert id1 == id2
    budgets = list_budgets(conn, month=MAR)
    assert len(budgets) == 1
    assert budgets[0].amount == Decimal("3200.00")


def test_set_budget_different_months_are_separate(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    salary_id = _cat_id(conn, "Salary")
    set_budget(conn, salary_id, FEB, Decimal("3000.00"))
    set_budget(conn, salary_id, MAR, Decimal("3000.00"))

    assert len(list_budgets(conn)) == 2


def test_set_budget_unknown_category_raises_key_error(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(KeyError, match="no-such-cat"):
        set_budget(conn, "no-such-cat", MAR, Decimal("100.00"))


def test_set_budget_expense_uses_negative_amount(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    groceries_id = _cat_id(conn, "Groceries")
    set_budget(conn, groceries_id, MAR, Decimal("-300.00"))
    b = list_budgets(conn, month=MAR)[0]
    assert b.amount == Decimal("-300.00")


# ---------------------------------------------------------------------------
# list_budgets
# ---------------------------------------------------------------------------


def test_list_budgets_returns_list_of_budget(conn: duckdb.DuckDBPyConnection) -> None:
    salary_id = _cat_id(conn, "Salary")
    set_budget(conn, salary_id, MAR, Decimal("3000.00"))
    budgets = list_budgets(conn)
    assert isinstance(budgets, list)
    assert all(isinstance(b, Budget) for b in budgets)


def test_list_budgets_empty_returns_empty(conn: duckdb.DuckDBPyConnection) -> None:
    assert list_budgets(conn) == []


def test_list_budgets_month_filter(conn: duckdb.DuckDBPyConnection) -> None:
    salary_id = _cat_id(conn, "Salary")
    groceries_id = _cat_id(conn, "Groceries")
    set_budget(conn, salary_id, FEB, Decimal("3000.00"))
    set_budget(conn, salary_id, MAR, Decimal("3000.00"))
    set_budget(conn, groceries_id, MAR, Decimal("-300.00"))

    mar_budgets = list_budgets(conn, month=MAR)
    assert len(mar_budgets) == 2
    assert all(b.month == MAR for b in mar_budgets)


def test_list_budgets_ordered_by_month_then_category(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    salary_id = _cat_id(conn, "Salary")
    groceries_id = _cat_id(conn, "Groceries")
    set_budget(conn, groceries_id, MAR, Decimal("-300.00"))
    set_budget(conn, salary_id, FEB, Decimal("3000.00"))
    set_budget(conn, salary_id, MAR, Decimal("3000.00"))

    budgets = list_budgets(conn)
    months = [b.month for b in budgets]
    assert months == sorted(months)


# ---------------------------------------------------------------------------
# get_budget_vs_actual
# ---------------------------------------------------------------------------


def test_get_budget_vs_actual_returns_list(conn: duckdb.DuckDBPyConnection) -> None:
    salary_id = _cat_id(conn, "Salary")
    set_budget(conn, salary_id, MAR, Decimal("3000.00"))
    result = get_budget_vs_actual(conn, MAR)
    assert isinstance(result, list)
    assert all(isinstance(r, BudgetVsActual) for r in result)


def test_get_budget_vs_actual_no_budgets_returns_empty(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    assert get_budget_vs_actual(conn, MAR) == []


def test_get_budget_vs_actual_no_transactions_actual_is_zero(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    salary_id = _cat_id(conn, "Salary")
    set_budget(conn, salary_id, MAR, Decimal("3000.00"))

    result = get_budget_vs_actual(conn, MAR)
    assert len(result) == 1
    r = result[0]
    assert r.actual == Decimal("0.00")
    assert r.variance == Decimal("-3000.00")  # 0 - 3000 = -3000 (missed income)


def test_get_budget_vs_actual_known_values(
    ccf_populated: duckdb.DuckDBPyConnection,
) -> None:
    # Assign the salary transaction (Feb, +2850) to the Salary category
    salary_cat_id = _cat_id(ccf_populated, "Salary")
    salary_txn_id = str(
        ccf_populated.execute(
            "SELECT id FROM transactions WHERE description LIKE '%SALAIRE%'"
        ).fetchone()[0]  # type: ignore[index]
    )
    update_category(ccf_populated, salary_txn_id, salary_cat_id)

    # Budget salary in February at 3000
    set_budget(ccf_populated, salary_cat_id, FEB, Decimal("3000.00"))

    result = get_budget_vs_actual(ccf_populated, FEB)
    assert len(result) == 1
    r = result[0]
    assert r.category_name == "Salary"
    assert r.direction == "income"
    assert r.budgeted == Decimal("3000.00")
    assert r.actual == Decimal("2850.00")
    assert r.variance == Decimal(
        "-150.00"
    )  # 2850 - 3000 = -150 (earned less than planned)
    # pct_used = 2850 / 3000 = 0.9500
    assert r.pct_used == Decimal("0.9500")


def test_get_budget_vs_actual_expense_category(
    ccf_populated: duckdb.DuckDBPyConnection,
) -> None:
    # Assign RATP (-86.40) to Transport
    transport_id = _cat_id(ccf_populated, "Transport")
    ratp_id = str(
        ccf_populated.execute(
            "SELECT id FROM transactions WHERE description LIKE '%RATP%'"
        ).fetchone()[0]  # type: ignore[index]
    )
    update_category(ccf_populated, ratp_id, transport_id)

    # Budget transport at -100 (€100 planned spend)
    set_budget(ccf_populated, transport_id, MAR, Decimal("-100.00"))
    result = get_budget_vs_actual(ccf_populated, MAR)

    transport_row = next(r for r in result if r.category_name == "Transport")
    assert transport_row.budgeted == Decimal("-100.00")
    assert transport_row.actual == Decimal("-86.40")
    assert transport_row.variance == Decimal(
        "13.60"
    )  # -86.40 - (-100) = +13.60 underspent
    assert transport_row.pct_used == Decimal("0.8640")  # 86.40 / 100 = 0.864


def test_get_budget_vs_actual_pct_used_none_when_budgeted_zero(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    salary_id = _cat_id(conn, "Salary")
    set_budget(conn, salary_id, MAR, Decimal("0.00"))
    result = get_budget_vs_actual(conn, MAR)
    assert len(result) == 1
    assert result[0].pct_used is None


def test_get_budget_vs_actual_uncategorised_transactions_excluded(
    ccf_populated: duckdb.DuckDBPyConnection,
) -> None:
    # All CCF transactions are uncategorised; set a salary budget for March
    salary_id = _cat_id(ccf_populated, "Salary")
    set_budget(ccf_populated, salary_id, MAR, Decimal("3000.00"))

    result = get_budget_vs_actual(ccf_populated, MAR)
    assert len(result) == 1
    # No transactions are categorised as Salary in March → actual=0
    assert result[0].actual == Decimal("0.00")
