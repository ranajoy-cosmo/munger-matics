"""Tests for get_savings_rate_history and get_spending_runway (Phase 10)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Generator

import duckdb
import pytest

from munger_matics.accounts import AccountType, add_account
from munger_matics.database.schema import initialise
from munger_matics.transactions import (
    SavingsRatePoint,
    get_savings_rate_history,
    get_spending_runway,
    insert_transactions,
    parse_csv,
    load_mapping,
)
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"
CCF_FIXTURE = FIXTURES / "sample_ccf.csv"
LIVRET_A_FIXTURE = FIXTURES / "sample_livret_a.csv"
TOML_CONFIG = Path(__file__).parent.parent.parent / "config" / "csv_mappings.toml"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    c = duckdb.connect(":memory:")
    initialise(c)
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


# ---------------------------------------------------------------------------
# get_savings_rate_history — return type
# ---------------------------------------------------------------------------


def test_savings_rate_history_returns_list(
    ccf_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = get_savings_rate_history(ccf_populated)
    assert isinstance(result, list)
    assert all(isinstance(p, SavingsRatePoint) for p in result)


def test_savings_rate_history_empty_db_returns_empty(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    assert get_savings_rate_history(conn) == []


def test_savings_rate_history_ordered_by_month(
    both_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = get_savings_rate_history(both_populated)
    months = [p.month for p in result]
    assert months == sorted(months)


# ---------------------------------------------------------------------------
# get_savings_rate_history — known values (CCF fixture)
#
#   Feb 2026: income=2850.00, net=2850.00  → savings_rate=1.0000
#   Mar 2026: income=506.20,  net=58.37    → savings_rate=58.37/506.20≈0.1153
# ---------------------------------------------------------------------------


def test_savings_rate_history_ccf_february(
    ccf_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    result = get_savings_rate_history(ccf_populated, account_id=ccf_id)
    feb = next(p for p in result if p.month == date(2026, 2, 1))
    assert feb.income == Decimal("2850.00")
    assert feb.net == Decimal("2850.00")
    assert feb.savings_rate == Decimal("1.0000")


def test_savings_rate_history_ccf_march(
    ccf_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    result = get_savings_rate_history(ccf_populated, account_id=ccf_id)
    mar = next(p for p in result if p.month == date(2026, 3, 1))
    assert mar.income == Decimal("506.20")
    assert mar.net == Decimal("58.37")
    # 58.37 / 506.20 = 0.1153 to 4dp
    assert mar.savings_rate == (Decimal("58.37") / Decimal("506.20")).quantize(
        Decimal("0.0001")
    )


def test_savings_rate_history_none_when_no_income(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # An account with only debit transactions → income=0 → savings_rate=None
    acc_id = add_account(conn, "Expense-only", AccountType.CHECKING)
    conn.execute(
        "INSERT INTO transactions (account_id, date, amount, description) "
        "VALUES (?, '2026-03-15', -200, 'rent')",
        [acc_id],
    )
    result = get_savings_rate_history(conn, account_id=acc_id)
    assert len(result) == 1
    assert result[0].savings_rate is None


def test_savings_rate_history_all_accounts(
    both_populated: duckdb.DuckDBPyConnection,
) -> None:
    # Without account_id, aggregates across all accounts
    result = get_savings_rate_history(both_populated)
    # CCF has Feb+Mar; Livret A has Dec+Jan+Feb+Mar+Apr → 5 months total
    assert len(result) == 5


def test_savings_rate_history_account_filter(
    both_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    result = get_savings_rate_history(both_populated, account_id=ccf_id)
    assert len(result) == 2
    months = {p.month for p in result}
    assert months == {date(2026, 2, 1), date(2026, 3, 1)}


# ---------------------------------------------------------------------------
# get_spending_runway — error cases
# ---------------------------------------------------------------------------


def test_spending_runway_unknown_account_raises_key_error(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(KeyError, match="no-such-id"):
        get_spending_runway(conn, "no-such-id")


def test_spending_runway_no_transactions_raises_value_error(
    conn: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    with pytest.raises(ValueError, match="No transactions"):
        get_spending_runway(conn, ccf_id)


def test_spending_runway_no_expenses_raises_value_error(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    acc_id = add_account(conn, "Credit-only", AccountType.SAVINGS)
    conn.execute(
        "INSERT INTO transactions (account_id, date, amount, description) "
        "VALUES (?, '2026-03-01', 500, 'income')",
        [acc_id],
    )
    with pytest.raises(ValueError, match="No expense data"):
        get_spending_runway(conn, acc_id)


# ---------------------------------------------------------------------------
# get_spending_runway — return type
# ---------------------------------------------------------------------------


def test_spending_runway_returns_decimal(
    ccf_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    result = get_spending_runway(ccf_populated, ccf_id)
    assert isinstance(result, Decimal)


# ---------------------------------------------------------------------------
# get_spending_runway — known values (CCF fixture)
#
#   Current balance = 2908.37
#   Lookback window (3 months back from Mar 2026): Jan–Mar 2026
#   Only Mar has expenses: 447.83
#   Avg monthly expenses = 447.83
#   Runway = 2908.37 / 447.83 ≈ 6.49
# ---------------------------------------------------------------------------


def test_spending_runway_ccf_known_value(
    ccf_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    result = get_spending_runway(ccf_populated, ccf_id)
    expected = (Decimal("2908.37") / Decimal("447.83")).quantize(Decimal("0.01"))
    assert result == expected


def test_spending_runway_lookback_months_parameter(
    ccf_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    # lookback_months=1: only March included; same result for CCF since Feb has no expenses
    result_3 = get_spending_runway(ccf_populated, ccf_id, lookback_months=3)
    result_1 = get_spending_runway(ccf_populated, ccf_id, lookback_months=1)
    assert result_3 == result_1


def test_spending_runway_positive_when_balance_positive(
    ccf_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    assert get_spending_runway(ccf_populated, ccf_id) > Decimal("0")


def test_spending_runway_constructed_scenario(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # Simple controlled scenario: balance=600, expenses 200/month for 2 months → runway=3
    acc_id = add_account(
        conn, "Test", AccountType.CHECKING, opening_balance=Decimal("600")
    )
    conn.executemany(
        "INSERT INTO transactions (account_id, date, amount, description) VALUES (?, ?, ?, ?)",
        [
            [acc_id, "2026-02-15", -200, "rent"],
            [acc_id, "2026-03-15", -200, "rent"],
        ],
    )
    # balance = 600 + (-200) + (-200) = 200
    # avg monthly expenses = (200+200)/2 = 200
    # runway = 200 / 200 = 1.00
    result = get_spending_runway(conn, acc_id)
    assert result == Decimal("1.00")
