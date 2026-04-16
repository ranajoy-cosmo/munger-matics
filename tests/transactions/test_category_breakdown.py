"""Tests for get_category_breakdown (Phase 9)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Generator

import duckdb
import pytest

from munger_matics.accounts import AccountType, add_account
from munger_matics.categories import seed_categories
from munger_matics.database.schema import initialise
from munger_matics.transactions import (
    CategoryBreakdown,
    get_category_breakdown,
    insert_transactions,
    parse_csv,
    load_mapping,
    update_category,
)
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"
CCF_FIXTURE = FIXTURES / "sample_ccf.csv"
LIVRET_A_FIXTURE = FIXTURES / "sample_livret_a.csv"
TOML_CONFIG = Path(__file__).parent.parent.parent / "config" / "csv_mappings.toml"
CATEGORIES_CONFIG = (
    Path(__file__).parent.parent.parent / "config" / "default_categories.toml"
)


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
def livret_id(conn: duckdb.DuckDBPyConnection) -> str:
    return add_account(conn, "Livret A", AccountType.SAVINGS)


@pytest.fixture
def ccf_populated(
    conn: duckdb.DuckDBPyConnection, ccf_id: str
) -> duckdb.DuckDBPyConnection:
    """DB with CCF fixture only (all transactions uncategorised)."""
    insert_transactions(
        conn, parse_csv(CCF_FIXTURE, ccf_id, load_mapping("ccf_checking", TOML_CONFIG))
    )
    return conn


@pytest.fixture
def both_populated(
    conn: duckdb.DuckDBPyConnection, ccf_id: str, livret_id: str
) -> duckdb.DuckDBPyConnection:
    insert_transactions(
        conn, parse_csv(CCF_FIXTURE, ccf_id, load_mapping("ccf_checking", TOML_CONFIG))
    )
    mapping = load_mapping("ccf_livret_a", TOML_CONFIG)
    insert_transactions(conn, parse_csv(LIVRET_A_FIXTURE, livret_id, mapping))
    return conn


def _salary_cat_id(conn: duckdb.DuckDBPyConnection) -> str:
    row = conn.execute("SELECT id FROM categories WHERE name = 'Salary'").fetchone()
    assert row is not None
    return str(row[0])


def _transport_cat_id(conn: duckdb.DuckDBPyConnection) -> str:
    row = conn.execute("SELECT id FROM categories WHERE name = 'Transport'").fetchone()
    assert row is not None
    return str(row[0])


def _first_txn_id(conn: duckdb.DuckDBPyConnection, account_id: str) -> str:
    """Return the id of the earliest transaction in the given account."""
    row = conn.execute(
        "SELECT id FROM transactions WHERE account_id = ? ORDER BY date LIMIT 1",
        [account_id],
    ).fetchone()
    assert row is not None
    return str(row[0])


# ---------------------------------------------------------------------------
# Return type and empty cases
# ---------------------------------------------------------------------------


def test_get_category_breakdown_returns_list(
    ccf_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = get_category_breakdown(ccf_populated)
    assert isinstance(result, list)
    assert all(isinstance(r, CategoryBreakdown) for r in result)


def test_get_category_breakdown_empty_db_returns_empty(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    result = get_category_breakdown(conn)
    assert result == []


# ---------------------------------------------------------------------------
# Uncategorised transactions appear as None category
# ---------------------------------------------------------------------------


def test_uncategorised_rows_have_none_fields(
    ccf_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = get_category_breakdown(ccf_populated)
    # All CCF rows are uncategorised
    for row in result:
        assert row.category_id is None
        assert row.category_name is None
        assert row.direction is None


def test_uncategorised_ccf_monthly_totals(
    ccf_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = get_category_breakdown(ccf_populated)
    by_month = {r.month: r.amount for r in result}
    # Feb: salary +2850.00 only
    assert by_month[date(2026, 2, 1)] == Decimal("2850.00")
    # Mar net: +506.20 credits - 447.83 debits = +58.37
    assert by_month[date(2026, 3, 1)] == Decimal("58.37")


# ---------------------------------------------------------------------------
# Categorised transactions split correctly
# ---------------------------------------------------------------------------


def test_categorised_row_splits_from_uncategorised(
    ccf_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    # Assign Salary to the single Feb transaction (salary row)
    salary_id = _salary_cat_id(ccf_populated)
    feb_txn_id = _first_txn_id(ccf_populated, ccf_id)
    update_category(ccf_populated, feb_txn_id, salary_id)

    result = get_category_breakdown(ccf_populated)
    feb_rows = [r for r in result if r.month == date(2026, 2, 1)]

    # Feb now has exactly one row: Salary (the only Feb transaction)
    assert len(feb_rows) == 1
    sal_row = feb_rows[0]
    assert sal_row.category_id == salary_id
    assert sal_row.category_name == "Salary"
    assert sal_row.direction == "income"
    assert sal_row.amount == Decimal("2850.00")


def test_multiple_categories_in_same_month(
    ccf_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    # Assign Salary to Feb txn, Transport to the first March txn (RATP, -86.40)
    salary_id = _salary_cat_id(ccf_populated)
    transport_id = _transport_cat_id(ccf_populated)

    feb_txn_id = _first_txn_id(ccf_populated, ccf_id)
    update_category(ccf_populated, feb_txn_id, salary_id)

    ratp_id = str(
        ccf_populated.execute(
            "SELECT id FROM transactions WHERE description LIKE '%RATP%'"
        ).fetchone()[0]  # type: ignore[index]
    )
    update_category(ccf_populated, ratp_id, transport_id)

    result = get_category_breakdown(ccf_populated)
    mar_rows = {r.category_name: r for r in result if r.month == date(2026, 3, 1)}

    # March has at least two distinct groups: Transport and uncategorised
    assert "Transport" in mar_rows
    assert None in mar_rows
    assert mar_rows["Transport"].amount == Decimal("-86.40")
    # Remaining March rows roll into the None (uncategorised) group
    assert mar_rows[None].amount == Decimal("58.37") - Decimal("-86.40")


# ---------------------------------------------------------------------------
# amount field
# ---------------------------------------------------------------------------


def test_amount_is_decimal(
    ccf_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = get_category_breakdown(ccf_populated)
    assert all(isinstance(r.amount, Decimal) for r in result)


def test_amount_sign_convention(
    ccf_populated: duckdb.DuckDBPyConnection,
) -> None:
    # Feb has one credit (+2850) → positive; all debits are in March → negative net possible
    result = get_category_breakdown(ccf_populated)
    by_month = {r.month: r.amount for r in result}
    assert by_month[date(2026, 2, 1)] > Decimal("0")


# ---------------------------------------------------------------------------
# date_from / date_to filters
# ---------------------------------------------------------------------------


def test_date_from_excludes_earlier_months(
    both_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = get_category_breakdown(both_populated, date_from=date(2026, 3, 1))
    months = {r.month for r in result}
    assert date(2025, 12, 1) not in months
    assert date(2026, 1, 1) not in months
    assert date(2026, 2, 1) not in months
    assert date(2026, 3, 1) in months


def test_date_to_excludes_later_months(
    both_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = get_category_breakdown(both_populated, date_to=date(2026, 1, 31))
    months = {r.month for r in result}
    assert date(2025, 12, 1) in months
    assert date(2026, 1, 1) in months
    assert date(2026, 2, 1) not in months


def test_date_range_filter(
    both_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = get_category_breakdown(
        both_populated,
        date_from=date(2026, 2, 1),
        date_to=date(2026, 3, 31),
    )
    months = {r.month for r in result}
    assert months == {date(2026, 2, 1), date(2026, 3, 1)}


# ---------------------------------------------------------------------------
# account_id filter
# ---------------------------------------------------------------------------


def test_account_id_filter_restricts_to_one_account(
    both_populated: duckdb.DuckDBPyConnection, ccf_id: str, livret_id: str
) -> None:
    ccf_result = get_category_breakdown(both_populated, account_id=ccf_id)
    livret_result = get_category_breakdown(both_populated, account_id=livret_id)

    # CCF has Feb and Mar months only
    ccf_months = {r.month for r in ccf_result}
    assert ccf_months == {date(2026, 2, 1), date(2026, 3, 1)}

    # Livret A has Dec 2025 through Apr 2026
    livret_months = {r.month for r in livret_result}
    assert date(2025, 12, 1) in livret_months
    assert date(2026, 4, 1) in livret_months
    assert date(2026, 2, 1) not in ccf_months or date(2026, 2, 1) in ccf_months
    # Livret months don't bleed into CCF result
    for r in ccf_result:
        assert date(2025, 12, 1) not in ccf_months


def test_account_id_totals_match_monthly_summary(
    ccf_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    from munger_matics.transactions import get_monthly_summary

    breakdown = get_category_breakdown(ccf_populated, account_id=ccf_id)
    summary = get_monthly_summary(ccf_populated, account_id=ccf_id)

    # Sum of breakdown amounts per month must equal summary net for that month
    from collections import defaultdict

    breakdown_net: dict[date, Decimal] = defaultdict(Decimal)
    for r in breakdown:
        breakdown_net[r.month] += r.amount

    for s in summary:
        assert breakdown_net[s.month] == s.net


# ---------------------------------------------------------------------------
# ordering
# ---------------------------------------------------------------------------


def test_results_ordered_by_month_ascending(
    both_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = get_category_breakdown(both_populated)
    months = [r.month for r in result]
    assert months == sorted(months)
