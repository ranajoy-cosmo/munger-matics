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
    MonthlySummary,
    Transaction,
    get_monthly_summary,
    get_transaction,
    insert_transactions,
    list_transactions,
    load_mapping,
    mark_transfer,
    parse_csv,
    update_category,
)
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"
CCF_FIXTURE = FIXTURES / "sample_ccf.csv"
LIVRET_A_FIXTURE = FIXTURES / "sample_livret_a.csv"
CATEGORIES_CONFIG = (
    Path(__file__).parent.parent.parent / "config" / "default_categories.toml"
)
TOML_CONFIG = Path(__file__).parent.parent.parent / "config" / "csv_mappings.toml"


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
def ccf_account(conn: duckdb.DuckDBPyConnection) -> str:
    return add_account(conn, "CCF Checking", AccountType.CHECKING)


@pytest.fixture
def populated(
    conn: duckdb.DuckDBPyConnection, ccf_account: str
) -> duckdb.DuckDBPyConnection:
    """DB with 15 CCF transactions inserted."""
    df = parse_csv(CCF_FIXTURE, ccf_account, load_mapping("ccf_checking", TOML_CONFIG))
    insert_transactions(conn, df)
    return conn


def _scalar(row: tuple[object, ...] | None) -> object:
    assert row is not None
    return row[0]


def _first_id(conn: duckdb.DuckDBPyConnection) -> str:
    result = _scalar(
        conn.execute("SELECT id FROM transactions ORDER BY date LIMIT 1").fetchone()
    )
    return str(result)


# ---------------------------------------------------------------------------
# get_transaction
# ---------------------------------------------------------------------------


def test_get_transaction_returns_transaction(
    populated: duckdb.DuckDBPyConnection,
) -> None:
    tid = _first_id(populated)
    t = get_transaction(populated, tid)
    assert isinstance(t, Transaction)
    assert t.id == tid


def test_get_transaction_fields(populated: duckdb.DuckDBPyConnection) -> None:
    tid = _first_id(populated)
    t = get_transaction(populated, tid)
    assert isinstance(t.amount, Decimal)
    assert isinstance(t.date, date)
    assert isinstance(t.description, str)
    assert t.source == "csv_import"


def test_get_transaction_not_found(conn: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(KeyError, match="not found"):
        get_transaction(conn, "00000000-0000-0000-0000-000000000000")


# ---------------------------------------------------------------------------
# list_transactions — no filters
# ---------------------------------------------------------------------------


def test_list_transactions_all(populated: duckdb.DuckDBPyConnection) -> None:
    txns = list_transactions(populated)
    assert len(txns) == 15


def test_list_transactions_ordered_date_desc(
    populated: duckdb.DuckDBPyConnection,
) -> None:
    txns = list_transactions(populated)
    dates = [t.date for t in txns]
    assert dates == sorted(dates, reverse=True)


def test_list_transactions_empty_db(conn: duckdb.DuckDBPyConnection) -> None:
    assert list_transactions(conn) == []


# ---------------------------------------------------------------------------
# list_transactions — filters
# ---------------------------------------------------------------------------


def test_filter_by_account_id(
    conn: duckdb.DuckDBPyConnection,
    ccf_account: str,
) -> None:
    livret_id = add_account(conn, "Livret A", AccountType.SAVINGS)
    from munger_matics.transactions import parse_csv, load_mapping, insert_transactions
    from pathlib import Path

    toml = Path(__file__).parent.parent.parent / "config/csv_mappings.toml"
    df_ccf = parse_csv(
        CCF_FIXTURE, ccf_account, load_mapping("ccf_checking", TOML_CONFIG)
    )
    df_la = parse_csv(LIVRET_A_FIXTURE, livret_id, load_mapping("ccf_livret_a", toml))
    insert_transactions(conn, df_ccf)
    insert_transactions(conn, df_la)
    ccf_txns = list_transactions(conn, account_id=ccf_account)
    la_txns = list_transactions(conn, account_id=livret_id)
    assert len(ccf_txns) == 15
    assert len(la_txns) == 10
    assert all(t.account_id == ccf_account for t in ccf_txns)


def test_filter_date_from(populated: duckdb.DuckDBPyConnection) -> None:
    txns = list_transactions(populated, date_from=date(2026, 3, 20))
    assert all(t.date >= date(2026, 3, 20) for t in txns)
    assert len(txns) > 0


def test_filter_date_to(populated: duckdb.DuckDBPyConnection) -> None:
    txns = list_transactions(populated, date_to=date(2026, 3, 5))
    assert all(t.date <= date(2026, 3, 5) for t in txns)
    assert len(txns) > 0


def test_filter_date_range(populated: duckdb.DuckDBPyConnection) -> None:
    txns = list_transactions(
        populated,
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 15),
    )
    assert all(date(2026, 3, 1) <= t.date <= date(2026, 3, 15) for t in txns)


def test_filter_search(populated: duckdb.DuckDBPyConnection) -> None:
    txns = list_transactions(populated, search="RATP")
    assert len(txns) == 1
    assert "RATP" in txns[0].description


def test_filter_search_case_insensitive(populated: duckdb.DuckDBPyConnection) -> None:
    txns_upper = list_transactions(populated, search="ratp")
    txns_lower = list_transactions(populated, search="RATP")
    assert len(txns_upper) == len(txns_lower)


def test_filter_uncategorised_only(
    populated: duckdb.DuckDBPyConnection, ccf_account: str
) -> None:
    # By default all are uncategorised
    all_txns = list_transactions(populated)
    uncategorised = list_transactions(populated, uncategorised_only=True)
    assert len(uncategorised) == len(all_txns)


def test_filter_uncategorised_reduces_after_categorise(
    populated: duckdb.DuckDBPyConnection,
) -> None:
    tid = _first_id(populated)
    cat_id = str(
        _scalar(
            populated.execute(
                "SELECT id FROM categories WHERE name = 'Salary'"
            ).fetchone()
        )
    )
    update_category(populated, tid, cat_id)
    uncategorised = list_transactions(populated, uncategorised_only=True)
    assert all(t.id != tid for t in uncategorised)


def test_filter_by_category_id(
    populated: duckdb.DuckDBPyConnection,
) -> None:
    tid = _first_id(populated)
    cat_id = str(
        _scalar(
            populated.execute(
                "SELECT id FROM categories WHERE name = 'Transport'"
            ).fetchone()
        )
    )
    update_category(populated, tid, cat_id)
    result = list_transactions(populated, category_id=cat_id)
    assert len(result) == 1
    assert result[0].category_id == cat_id


def test_limit(populated: duckdb.DuckDBPyConnection) -> None:
    txns = list_transactions(populated, limit=5)
    assert len(txns) == 5


# ---------------------------------------------------------------------------
# update_category
# ---------------------------------------------------------------------------


def test_update_category_sets_category_id(
    populated: duckdb.DuckDBPyConnection,
) -> None:
    tid = _first_id(populated)
    cat_id = str(
        _scalar(
            populated.execute(
                "SELECT id FROM categories WHERE name = 'Salary'"
            ).fetchone()
        )
    )
    update_category(populated, tid, cat_id)
    t = get_transaction(populated, tid)
    assert t.category_id == cat_id


def test_update_category_clear_sets_null(
    populated: duckdb.DuckDBPyConnection,
) -> None:
    tid = _first_id(populated)
    cat_id = str(
        _scalar(populated.execute("SELECT id FROM categories LIMIT 1").fetchone())
    )
    update_category(populated, tid, cat_id)
    update_category(populated, tid, None)
    t = get_transaction(populated, tid)
    assert t.category_id is None


def test_update_category_unknown_transaction(conn: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(KeyError, match="Transaction not found"):
        update_category(conn, "00000000-0000-0000-0000-000000000000", None)


def test_update_category_unknown_category(
    populated: duckdb.DuckDBPyConnection,
) -> None:
    tid = _first_id(populated)
    with pytest.raises(KeyError, match="Category not found"):
        update_category(populated, tid, "00000000-0000-0000-0000-000000000000")


# ---------------------------------------------------------------------------
# mark_transfer
# ---------------------------------------------------------------------------


def test_mark_transfer_sets_flags(populated: duckdb.DuckDBPyConnection) -> None:
    ids = [
        str(r[0])
        for r in populated.execute(
            "SELECT id FROM transactions ORDER BY date LIMIT 2"
        ).fetchall()
    ]
    id_a, id_b = ids
    mark_transfer(populated, id_a, id_b)
    ta = get_transaction(populated, id_a)
    tb = get_transaction(populated, id_b)
    assert ta.is_transfer is True
    assert ta.transfer_peer_id == id_b
    assert tb.is_transfer is True
    assert tb.transfer_peer_id == id_a


def test_mark_transfer_unknown_transaction(
    populated: duckdb.DuckDBPyConnection,
) -> None:
    tid = _first_id(populated)
    with pytest.raises(KeyError):
        mark_transfer(populated, tid, "00000000-0000-0000-0000-000000000000")


# ---------------------------------------------------------------------------
# get_monthly_summary
# ---------------------------------------------------------------------------


def test_monthly_summary_returns_list(populated: duckdb.DuckDBPyConnection) -> None:
    summaries = get_monthly_summary(populated)
    assert isinstance(summaries, list)
    assert len(summaries) > 0
    assert all(isinstance(s, MonthlySummary) for s in summaries)


def test_monthly_summary_month_is_first_of_month(
    populated: duckdb.DuckDBPyConnection,
) -> None:
    for s in get_monthly_summary(populated):
        assert s.month.day == 1


def test_monthly_summary_income_non_negative(
    populated: duckdb.DuckDBPyConnection,
) -> None:
    for s in get_monthly_summary(populated):
        assert s.income >= Decimal("0")


def test_monthly_summary_expenses_non_positive(
    populated: duckdb.DuckDBPyConnection,
) -> None:
    for s in get_monthly_summary(populated):
        assert s.expenses <= Decimal("0")


def test_monthly_summary_net_equals_income_plus_expenses(
    populated: duckdb.DuckDBPyConnection,
) -> None:
    for s in get_monthly_summary(populated):
        assert s.net == s.income + s.expenses


def test_monthly_summary_known_values(
    populated: duckdb.DuckDBPyConnection,
) -> None:
    # CCF fixture date breakdown:
    #   Feb 2026 (date_operation = 28/02/2026):
    #     income:  salary 2850.00
    #     expenses: none
    #     net: 2850.00
    #
    #   Mar 2026 (all remaining rows):
    #     income:  Decathlon refund 5.00 + Livret A transfer 500.00 + interest 1.20 = 506.20
    #     expenses: RATP 86.40 + EDF 127.50 + Restaurant 34.20 + Amazon 67.89
    #               + Pharmacy 12.40 + Grand Frais 23.95 + Boulangerie×2 30.00
    #               + Netflix 17.99 + AXA 45.00 + Frais 2.50 = 447.83
    #     net: 506.20 - 447.83 = 58.37

    summaries = {s.month: s for s in get_monthly_summary(populated)}

    feb = summaries.get(date(2026, 2, 1))
    assert feb is not None
    assert feb.income == Decimal("2850.00")
    assert feb.expenses == Decimal("0.00")
    assert feb.net == Decimal("2850.00")

    march = summaries.get(date(2026, 3, 1))
    assert march is not None
    assert march.income == Decimal("506.20")
    assert march.expenses == Decimal("-447.83")
    assert march.net == Decimal("58.37")


def test_monthly_summary_filtered_by_account(
    conn: duckdb.DuckDBPyConnection, ccf_account: str
) -> None:
    livret_id = add_account(conn, "Livret A", AccountType.SAVINGS)
    from munger_matics.transactions import parse_csv, load_mapping
    from pathlib import Path

    toml = Path(__file__).parent.parent.parent / "config/csv_mappings.toml"
    df_ccf = parse_csv(
        CCF_FIXTURE, ccf_account, load_mapping("ccf_checking", TOML_CONFIG)
    )
    df_la = parse_csv(LIVRET_A_FIXTURE, livret_id, load_mapping("ccf_livret_a", toml))
    insert_transactions(conn, df_ccf)
    insert_transactions(conn, df_la)

    all_summaries = get_monthly_summary(conn)
    ccf_summaries = get_monthly_summary(conn, account_id=ccf_account)

    # Filtered account_id field is populated
    assert all(s.account_id == ccf_account for s in ccf_summaries)
    # Totals differ because Livret A rows are excluded
    all_net = sum(s.net for s in all_summaries)
    ccf_net = sum(s.net for s in ccf_summaries)
    assert all_net != ccf_net
