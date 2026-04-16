"""Tests for the savings goals repository (Phase 12)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Generator

import duckdb
import pytest

from munger_matics.accounts import AccountType, add_account
from munger_matics.database.schema import initialise
from munger_matics.finance import (
    CompoundingFreq,
    fv_annuity,
    future_value_compound,
)
from munger_matics.savings_goals import (
    GoalProgress,
    SavingsGoal,
    add_goal,
    get_goal_progress,
    list_goals,
)
from munger_matics.transactions import insert_transactions, load_mapping, parse_csv
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"
CCF_FIXTURE = FIXTURES / "sample_ccf.csv"
TOML_CONFIG = Path(__file__).parent.parent.parent / "config" / "csv_mappings.toml"

AS_OF = date(2026, 4, 1)


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
def savings_account(conn: duckdb.DuckDBPyConnection) -> str:
    return add_account(
        conn,
        "Livret A",
        AccountType.SAVINGS,
        opening_balance=Decimal("5000.00"),
    )


# ---------------------------------------------------------------------------
# add_goal
# ---------------------------------------------------------------------------


def test_add_goal_returns_uuid(conn: duckdb.DuckDBPyConnection) -> None:
    goal_id = add_goal(conn, "Emergency fund", Decimal("10000.00"))
    assert isinstance(goal_id, str)
    assert len(goal_id) == 36


def test_add_goal_stores_all_fields(conn: duckdb.DuckDBPyConnection) -> None:
    goal_id = add_goal(
        conn,
        "Holiday",
        Decimal("3000.00"),
        target_date=date(2026, 12, 1),
    )
    goals = list_goals(conn)
    assert len(goals) == 1
    g = goals[0]
    assert g.id == goal_id
    assert g.name == "Holiday"
    assert g.target_amount == Decimal("3000.00")
    assert g.target_date == date(2026, 12, 1)


def test_add_goal_without_target_date(conn: duckdb.DuckDBPyConnection) -> None:
    add_goal(conn, "Open-ended", Decimal("50000.00"))
    goals = list_goals(conn)
    assert goals[0].target_date is None


def test_add_goal_non_positive_amount_raises(conn: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(ValueError, match="target_amount must be > 0"):
        add_goal(conn, "Bad", Decimal("0.00"))

    with pytest.raises(ValueError, match="target_amount must be > 0"):
        add_goal(conn, "Bad", Decimal("-100.00"))


# ---------------------------------------------------------------------------
# list_goals
# ---------------------------------------------------------------------------


def test_list_goals_empty(conn: duckdb.DuckDBPyConnection) -> None:
    assert list_goals(conn) == []


def test_list_goals_returns_list_of_savings_goal(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    add_goal(conn, "A", Decimal("1000.00"))
    result = list_goals(conn)
    assert isinstance(result, list)
    assert all(isinstance(g, SavingsGoal) for g in result)


def test_list_goals_ordered_by_target_date_nulls_last(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    add_goal(conn, "Open-ended", Decimal("1000.00"))  # no date
    add_goal(conn, "Short-term", Decimal("500.00"), target_date=date(2026, 6, 1))
    add_goal(conn, "Long-term", Decimal("20000.00"), target_date=date(2028, 1, 1))

    goals = list_goals(conn)
    dates = [g.target_date for g in goals]
    # Short-term, Long-term, Open-ended
    assert dates == [date(2026, 6, 1), date(2028, 1, 1), None]


# ---------------------------------------------------------------------------
# get_goal_progress — error cases
# ---------------------------------------------------------------------------


def test_goal_progress_unknown_goal_raises_key_error(
    conn: duckdb.DuckDBPyConnection, savings_account: str
) -> None:
    with pytest.raises(KeyError, match="no-such-goal"):
        get_goal_progress(
            conn,
            "no-such-goal",
            savings_account,
            monthly_contribution=Decimal("500"),
            annual_rate=Decimal("0.03"),
            as_of=AS_OF,
        )


def test_goal_progress_unknown_account_raises_key_error(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    goal_id = add_goal(conn, "Test", Decimal("10000.00"))
    with pytest.raises(KeyError):
        get_goal_progress(
            conn,
            goal_id,
            "no-such-account",
            monthly_contribution=Decimal("500"),
            annual_rate=Decimal("0.03"),
            as_of=AS_OF,
        )


def test_goal_progress_negative_contribution_raises(
    conn: duckdb.DuckDBPyConnection, savings_account: str
) -> None:
    goal_id = add_goal(conn, "Test", Decimal("10000.00"))
    with pytest.raises(ValueError, match="monthly_contribution"):
        get_goal_progress(
            conn,
            goal_id,
            savings_account,
            monthly_contribution=Decimal("-100"),
            annual_rate=Decimal("0.03"),
            as_of=AS_OF,
        )


# ---------------------------------------------------------------------------
# get_goal_progress — return type
# ---------------------------------------------------------------------------


def test_goal_progress_returns_goal_progress(
    conn: duckdb.DuckDBPyConnection, savings_account: str
) -> None:
    goal_id = add_goal(conn, "Test", Decimal("10000.00"), target_date=date(2026, 10, 1))
    result = get_goal_progress(
        conn,
        goal_id,
        savings_account,
        monthly_contribution=Decimal("500"),
        annual_rate=Decimal("0.05"),
        as_of=AS_OF,
    )
    assert isinstance(result, GoalProgress)
    assert isinstance(result.current_balance, Decimal)
    assert isinstance(result.projected_balance, Decimal)
    assert isinstance(result.on_track, bool)


# ---------------------------------------------------------------------------
# get_goal_progress — open-ended goal (no target_date)
# ---------------------------------------------------------------------------


def test_goal_progress_no_target_date(
    conn: duckdb.DuckDBPyConnection, savings_account: str
) -> None:
    goal_id = add_goal(conn, "Open", Decimal("10000.00"))
    result = get_goal_progress(
        conn,
        goal_id,
        savings_account,
        monthly_contribution=Decimal("500"),
        annual_rate=Decimal("0.05"),
        as_of=AS_OF,
    )
    assert result.months_remaining is None
    # No target date → project = current balance
    assert result.projected_balance == result.current_balance


# ---------------------------------------------------------------------------
# get_goal_progress — known projection values
#
# Setup:
#   opening_balance = 5000, no transactions → current_balance = 5000
#   as_of = 2026-04-01, target_date = 2026-10-01 → months_remaining = 6
#   annual_rate = 0.05, monthly_contribution = 500
#
# Expected:
#   fv_existing = future_value_compound(5000, 0.05, 6/12, MONTHLY)
#   fv_contributions = fv_annuity(500, 0.05, 6/12, MONTHLY)
#   projected = fv_existing + fv_contributions
# ---------------------------------------------------------------------------


def _expected_projected(
    balance: Decimal,
    rate: Decimal,
    contribution: Decimal,
    months: int,
) -> Decimal:
    years = float(months) / 12.0
    fv_e = future_value_compound(balance, rate, years, CompoundingFreq.MONTHLY)
    fv_c = fv_annuity(contribution, rate, years, CompoundingFreq.MONTHLY)
    return fv_e + fv_c


def test_goal_progress_current_balance_reflects_opening_balance(
    conn: duckdb.DuckDBPyConnection, savings_account: str
) -> None:
    goal_id = add_goal(conn, "Test", Decimal("10000.00"), target_date=date(2026, 10, 1))
    result = get_goal_progress(
        conn,
        goal_id,
        savings_account,
        monthly_contribution=Decimal("500"),
        annual_rate=Decimal("0.05"),
        as_of=AS_OF,
    )
    assert result.current_balance == Decimal("5000.00")


def test_goal_progress_months_remaining_correct(
    conn: duckdb.DuckDBPyConnection, savings_account: str
) -> None:
    goal_id = add_goal(conn, "Test", Decimal("10000.00"), target_date=date(2026, 10, 1))
    result = get_goal_progress(
        conn,
        goal_id,
        savings_account,
        monthly_contribution=Decimal("500"),
        annual_rate=Decimal("0.05"),
        as_of=AS_OF,
    )
    assert result.months_remaining == 6


def test_goal_progress_projected_balance_matches_finance_library(
    conn: duckdb.DuckDBPyConnection, savings_account: str
) -> None:
    rate = Decimal("0.05")
    contribution = Decimal("500")
    target_date = date(2026, 10, 1)
    goal_id = add_goal(conn, "Test", Decimal("10000.00"), target_date=target_date)

    result = get_goal_progress(
        conn,
        goal_id,
        savings_account,
        monthly_contribution=contribution,
        annual_rate=rate,
        as_of=AS_OF,
    )

    expected = _expected_projected(Decimal("5000.00"), rate, contribution, 6)
    assert result.projected_balance == expected


def test_goal_progress_on_track_false_when_insufficient(
    conn: duckdb.DuckDBPyConnection, savings_account: str
) -> None:
    # Target 20000; with 5000 balance and 500/month at 5% for 6 months → ~ 8158 → not on track
    goal_id = add_goal(
        conn, "Big target", Decimal("20000.00"), target_date=date(2026, 10, 1)
    )
    result = get_goal_progress(
        conn,
        goal_id,
        savings_account,
        monthly_contribution=Decimal("500"),
        annual_rate=Decimal("0.05"),
        as_of=AS_OF,
    )
    assert result.on_track is False


def test_goal_progress_on_track_true_when_already_there(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # Account with 10000 balance, target = 5000 → projected > target
    acc_id = add_account(
        conn, "Rich", AccountType.SAVINGS, opening_balance=Decimal("10000.00")
    )
    goal_id = add_goal(conn, "Easy", Decimal("5000.00"), target_date=date(2026, 10, 1))
    result = get_goal_progress(
        conn,
        goal_id,
        acc_id,
        monthly_contribution=Decimal("0"),
        annual_rate=Decimal("0.05"),
        as_of=AS_OF,
    )
    assert result.on_track is True


def test_goal_progress_past_deadline_projected_equals_current(
    conn: duckdb.DuckDBPyConnection, savings_account: str
) -> None:
    # target_date in the past → months_remaining <= 0 → no projection
    goal_id = add_goal(
        conn, "Overdue", Decimal("10000.00"), target_date=date(2025, 1, 1)
    )
    result = get_goal_progress(
        conn,
        goal_id,
        savings_account,
        monthly_contribution=Decimal("500"),
        annual_rate=Decimal("0.05"),
        as_of=AS_OF,
    )
    assert result.months_remaining is not None
    assert result.months_remaining <= 0
    assert result.projected_balance == result.current_balance


def test_goal_progress_with_real_transactions(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # Insert CCF transactions to verify current_balance reflects them
    ccf_id = add_account(conn, "CCF", AccountType.CHECKING)
    insert_transactions(
        conn, parse_csv(CCF_FIXTURE, ccf_id, load_mapping("ccf_checking", TOML_CONFIG))
    )

    goal_id = add_goal(conn, "Test", Decimal("5000.00"), target_date=date(2026, 10, 1))
    result = get_goal_progress(
        conn,
        goal_id,
        ccf_id,
        monthly_contribution=Decimal("200"),
        annual_rate=Decimal("0.02"),
        as_of=AS_OF,
    )
    # CCF balance: 0 (opening) + 2850 (Feb) + 58.37 (Mar net) = 2908.37
    assert result.current_balance == Decimal("2908.37")
