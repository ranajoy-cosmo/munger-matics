"""Tests for balance_history and net_worth_history."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Generator

import duckdb
import pytest

from munger_matics.accounts import (
    AccountType,
    BalancePoint,
    NetWorthPoint,
    add_account,
    balance_history,
    net_worth_history,
)
from munger_matics.database.schema import initialise
from munger_matics.transactions import (
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
def both_populated(
    conn: duckdb.DuckDBPyConnection, ccf_id: str, livret_id: str
) -> duckdb.DuckDBPyConnection:
    """DB with CCF (Feb–Mar 2026) and Livret A (Dec 2025–Apr 2026) inserted."""
    insert_transactions(
        conn, parse_csv(CCF_FIXTURE, ccf_id, load_mapping("ccf_checking", TOML_CONFIG))
    )
    mapping = load_mapping("ccf_livret_a", TOML_CONFIG)
    insert_transactions(conn, parse_csv(LIVRET_A_FIXTURE, livret_id, mapping))
    return conn


# ---------------------------------------------------------------------------
# balance_history — error handling
# ---------------------------------------------------------------------------


def test_balance_history_raises_for_unknown_account(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(KeyError, match="no-such-id"):
        balance_history(conn, "no-such-id")


def test_balance_history_empty_account_returns_empty_list(
    conn: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    # Account exists but has no transactions
    result = balance_history(conn, ccf_id)
    assert result == []


# ---------------------------------------------------------------------------
# balance_history — return type and structure
# ---------------------------------------------------------------------------


def test_balance_history_returns_list_of_balance_points(
    both_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    result = balance_history(both_populated, ccf_id)
    assert isinstance(result, list)
    assert all(isinstance(p, BalancePoint) for p in result)


def test_balance_history_account_id_matches(
    both_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    result = balance_history(both_populated, ccf_id)
    assert all(p.account_id == ccf_id for p in result)


def test_balance_history_ordered_ascending(
    both_populated: duckdb.DuckDBPyConnection, livret_id: str
) -> None:
    result = balance_history(both_populated, livret_id)
    months = [p.month for p in result]
    assert months == sorted(months)


def test_balance_history_balance_is_decimal(
    both_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    result = balance_history(both_populated, ccf_id)
    assert all(isinstance(p.balance, Decimal) for p in result)


# ---------------------------------------------------------------------------
# balance_history — known values (CCF fixture)
#
# CCF transactions (opening_balance=0):
#   Feb 2026: +2850.00 (salary)   → cumulative = 2850.00
#   Mar 2026: +58.37 net          → cumulative = 2908.37
# ---------------------------------------------------------------------------


def test_balance_history_ccf_month_count(
    both_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    result = balance_history(both_populated, ccf_id)
    assert len(result) == 2


def test_balance_history_ccf_february(
    both_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    result = balance_history(both_populated, ccf_id)
    feb = next(p for p in result if p.month == date(2026, 2, 1))
    # Salary +2850.00 in Feb; all other transactions are in March
    assert feb.balance == Decimal("2850.00")


def test_balance_history_ccf_march(
    both_populated: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    result = balance_history(both_populated, ccf_id)
    mar = next(p for p in result if p.month == date(2026, 3, 1))
    # Mar net: +506.20 credits - 447.83 debits = +58.37; total = 2908.37
    assert mar.balance == Decimal("2908.37")


# ---------------------------------------------------------------------------
# balance_history — known values (Livret A fixture)
#
# Livret A (opening_balance=0):
#   Dec 2025: +261.23             → 261.23
#   Jan 2026: +200.87             → 462.10
#   Feb 2026: +100.83             → 562.93
#   Mar 2026: -349.19             → 213.74
#   Apr 2026: -300.00             → -86.26
# ---------------------------------------------------------------------------


def test_balance_history_livret_month_count(
    both_populated: duckdb.DuckDBPyConnection, livret_id: str
) -> None:
    result = balance_history(both_populated, livret_id)
    assert len(result) == 5


def test_balance_history_livret_known_values(
    both_populated: duckdb.DuckDBPyConnection, livret_id: str
) -> None:
    result = balance_history(both_populated, livret_id)
    by_month = {p.month: p.balance for p in result}
    assert by_month[date(2025, 12, 1)] == Decimal("261.23")
    assert by_month[date(2026, 1, 1)] == Decimal("462.10")
    assert by_month[date(2026, 2, 1)] == Decimal("562.93")
    assert by_month[date(2026, 3, 1)] == Decimal("213.74")
    assert by_month[date(2026, 4, 1)] == Decimal("-86.26")


# ---------------------------------------------------------------------------
# balance_history — opening_balance is included in running total
# ---------------------------------------------------------------------------


def test_balance_history_includes_opening_balance(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    acc_id = add_account(
        conn, "With Opening", AccountType.SAVINGS, opening_balance=Decimal("500.00")
    )
    conn.execute(
        "INSERT INTO transactions (account_id, date, amount, description) "
        "VALUES (?, '2026-03-15', 200, 'deposit')",
        [acc_id],
    )
    result = balance_history(conn, acc_id)
    assert len(result) == 1
    # opening_balance 500 + transaction 200 = 700
    assert result[0].balance == Decimal("700.00")


# ---------------------------------------------------------------------------
# balance_history — date filters
# ---------------------------------------------------------------------------


def test_balance_history_date_from_filter(
    both_populated: duckdb.DuckDBPyConnection, livret_id: str
) -> None:
    # date_from=2026-02-01 should exclude Dec 2025 and Jan 2026
    result = balance_history(both_populated, livret_id, date_from=date(2026, 2, 1))
    months = [p.month for p in result]
    assert date(2025, 12, 1) not in months
    assert date(2026, 1, 1) not in months
    assert date(2026, 2, 1) in months


def test_balance_history_date_from_balance_is_cumulative(
    both_populated: duckdb.DuckDBPyConnection, livret_id: str
) -> None:
    # Even though we filter to Feb onwards, the Feb balance must include Dec/Jan history
    result = balance_history(both_populated, livret_id, date_from=date(2026, 2, 1))
    by_month = {p.month: p.balance for p in result}
    # Feb balance = 562.93 (cumulative from opening through Feb), not just Feb flow
    assert by_month[date(2026, 2, 1)] == Decimal("562.93")


def test_balance_history_date_to_filter(
    both_populated: duckdb.DuckDBPyConnection, livret_id: str
) -> None:
    result = balance_history(both_populated, livret_id, date_to=date(2026, 1, 31))
    months = [p.month for p in result]
    assert date(2025, 12, 1) in months
    assert date(2026, 1, 1) in months
    assert date(2026, 2, 1) not in months


def test_balance_history_date_range_filter(
    both_populated: duckdb.DuckDBPyConnection, livret_id: str
) -> None:
    result = balance_history(
        both_populated,
        livret_id,
        date_from=date(2026, 2, 1),
        date_to=date(2026, 3, 31),
    )
    months = [p.month for p in result]
    assert months == [date(2026, 2, 1), date(2026, 3, 1)]


# ---------------------------------------------------------------------------
# net_worth_history — basic cases
# ---------------------------------------------------------------------------


def test_net_worth_history_empty_db_returns_empty(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    result = net_worth_history(conn)
    assert result == []


def test_net_worth_history_no_transactions_returns_empty(
    conn: duckdb.DuckDBPyConnection, ccf_id: str
) -> None:
    # Account exists but no transactions → no months → empty
    result = net_worth_history(conn)
    assert result == []


def test_net_worth_history_returns_list_of_net_worth_points(
    both_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = net_worth_history(both_populated)
    assert isinstance(result, list)
    assert all(isinstance(p, NetWorthPoint) for p in result)


def test_net_worth_history_ordered_ascending(
    both_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = net_worth_history(both_populated)
    months = [p.month for p in result]
    assert months == sorted(months)


def test_net_worth_history_fields_are_decimal(
    both_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = net_worth_history(both_populated)
    for p in result:
        assert isinstance(p.assets, Decimal)
        assert isinstance(p.liabilities, Decimal)
        assert isinstance(p.net_worth, Decimal)


# ---------------------------------------------------------------------------
# net_worth_history — known values
#
# CCF (checking) + Livret A (savings), both opening_balance=0.
# CCF has transactions in Feb and Mar only; balance carries forward to Apr.
# Livret A has transactions Dec–Apr.
#
# Month-end balances:
#   Dec 2025 : CCF=0.00,     Livret=261.23  → nw=261.23
#   Jan 2026 : CCF=0.00,     Livret=462.10  → nw=462.10
#   Feb 2026 : CCF=2850.00,  Livret=562.93  → nw=3412.93
#   Mar 2026 : CCF=2908.37,  Livret=213.74  → nw=3122.11
#   Apr 2026 : CCF=2908.37,  Livret=-86.26  → nw=2822.11
# ---------------------------------------------------------------------------


def test_net_worth_history_month_count(
    both_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = net_worth_history(both_populated)
    assert len(result) == 5


def test_net_worth_history_known_values(
    both_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = net_worth_history(both_populated)
    by_month = {p.month: p for p in result}

    assert by_month[date(2025, 12, 1)].net_worth == Decimal("261.23")
    assert by_month[date(2026, 1, 1)].net_worth == Decimal("462.10")
    assert by_month[date(2026, 2, 1)].net_worth == Decimal("3412.93")
    assert by_month[date(2026, 3, 1)].net_worth == Decimal("3122.11")
    assert by_month[date(2026, 4, 1)].net_worth == Decimal("2822.11")


def test_net_worth_history_assets_are_checking_and_savings(
    both_populated: duckdb.DuckDBPyConnection,
) -> None:
    result = net_worth_history(both_populated)
    by_month = {p.month: p for p in result}
    # Both accounts are asset types; liabilities should be zero throughout
    for p in result:
        assert p.liabilities == Decimal("0.00")
    assert by_month[date(2026, 2, 1)].assets == Decimal("3412.93")


def test_net_worth_history_ccf_carries_forward_to_april(
    both_populated: duckdb.DuckDBPyConnection,
) -> None:
    # CCF has no April transactions but its March balance must carry to April
    result = net_worth_history(both_populated)
    by_month = {p.month: p for p in result}
    # April net_worth = CCF(2908.37) + Livret(-86.26) = 2822.11
    assert by_month[date(2026, 4, 1)].net_worth == Decimal("2822.11")


def test_net_worth_history_separates_assets_and_liabilities(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # Create one savings account (asset) and one loan account (liability)
    savings_id = add_account(
        conn, "Savings", AccountType.SAVINGS, opening_balance=Decimal("1000.00")
    )
    loan_id = add_account(
        conn, "Loan", AccountType.LOAN, opening_balance=Decimal("-5000.00")
    )
    conn.execute(
        "INSERT INTO transactions (account_id, date, amount, description) "
        "VALUES (?, '2026-03-01', 100, 'deposit')",
        [savings_id],
    )
    conn.execute(
        "INSERT INTO transactions (account_id, date, amount, description) "
        "VALUES (?, '2026-03-01', -200, 'interest')",
        [loan_id],
    )
    result = net_worth_history(conn)
    assert len(result) == 1
    p = result[0]
    assert p.assets == Decimal("1100.00")  # savings: 1000 + 100
    assert p.liabilities == Decimal("-5200.00")  # loan: -5000 + (-200)
    assert p.net_worth == Decimal("-4100.00")  # 1100 + (-5200)
