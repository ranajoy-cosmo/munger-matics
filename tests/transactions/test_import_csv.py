from __future__ import annotations

from pathlib import Path
from typing import Generator

import duckdb
import polars as pl
import pytest

from munger_matics.accounts import AccountType, add_account
from munger_matics.categories import seed_categories
from munger_matics.database.schema import initialise
from munger_matics.transactions import (
    InsertResult,
    insert_transactions,
    load_mapping,
    parse_csv,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent.parent / "fixtures"
CCF_FIXTURE = FIXTURES / "sample_ccf.csv"
LIVRET_A_FIXTURE = FIXTURES / "sample_livret_a.csv"
TOML_CONFIG = Path(__file__).parent.parent.parent / "config" / "csv_mappings.toml"
CATEGORIES_CONFIG = (
    Path(__file__).parent.parent.parent / "config" / "default_categories.toml"
)

CCF_ROW_COUNT = 15
LIVRET_A_ROW_COUNT = 10


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
def livret_a_account(conn: duckdb.DuckDBPyConnection) -> str:
    return add_account(conn, "Livret A", AccountType.SAVINGS)


def _scalar(row: tuple[object, ...] | None) -> object:
    assert row is not None
    return row[0]


# ---------------------------------------------------------------------------
# insert_transactions — basic
# ---------------------------------------------------------------------------


def test_insert_returns_insert_result(
    conn: duckdb.DuckDBPyConnection, ccf_account: str
) -> None:
    df = parse_csv(CCF_FIXTURE, ccf_account, load_mapping("ccf_checking", TOML_CONFIG))
    result = insert_transactions(conn, df)
    assert isinstance(result, InsertResult)


def test_insert_all_rows_on_first_import(
    conn: duckdb.DuckDBPyConnection, ccf_account: str
) -> None:
    df = parse_csv(CCF_FIXTURE, ccf_account, load_mapping("ccf_checking", TOML_CONFIG))
    result = insert_transactions(conn, df)
    assert result.rows_attempted == CCF_ROW_COUNT
    assert result.rows_inserted == CCF_ROW_COUNT
    assert result.rows_skipped == 0


def test_insert_result_invariant(
    conn: duckdb.DuckDBPyConnection, ccf_account: str
) -> None:
    # rows_attempted must always equal rows_inserted + rows_skipped
    df = parse_csv(CCF_FIXTURE, ccf_account, load_mapping("ccf_checking", TOML_CONFIG))
    result = insert_transactions(conn, df)
    assert result.rows_attempted == result.rows_inserted + result.rows_skipped


def test_rows_persisted_in_db(
    conn: duckdb.DuckDBPyConnection, ccf_account: str
) -> None:
    df = parse_csv(CCF_FIXTURE, ccf_account, load_mapping("ccf_checking", TOML_CONFIG))
    insert_transactions(conn, df)
    count = _scalar(conn.execute("SELECT COUNT(*) FROM transactions").fetchone())
    assert count == CCF_ROW_COUNT


# ---------------------------------------------------------------------------
# insert_transactions — deduplication
# ---------------------------------------------------------------------------


def test_reimport_skips_all_rows(
    conn: duckdb.DuckDBPyConnection, ccf_account: str
) -> None:
    df = parse_csv(CCF_FIXTURE, ccf_account, load_mapping("ccf_checking", TOML_CONFIG))
    insert_transactions(conn, df)
    result = insert_transactions(conn, df)
    assert result.rows_inserted == 0
    assert result.rows_skipped == CCF_ROW_COUNT


def test_reimport_does_not_duplicate_db_rows(
    conn: duckdb.DuckDBPyConnection, ccf_account: str
) -> None:
    df = parse_csv(CCF_FIXTURE, ccf_account, load_mapping("ccf_checking", TOML_CONFIG))
    insert_transactions(conn, df)
    insert_transactions(conn, df)
    count = _scalar(conn.execute("SELECT COUNT(*) FROM transactions").fetchone())
    assert count == CCF_ROW_COUNT


def test_partial_dedup(conn: duckdb.DuckDBPyConnection, ccf_account: str) -> None:
    # Insert only the first 5 rows, then insert all 15 — 10 should be new.
    df = parse_csv(CCF_FIXTURE, ccf_account, load_mapping("ccf_checking", TOML_CONFIG))
    first_five = df.head(5)
    insert_transactions(conn, first_five)
    result = insert_transactions(conn, df)
    assert result.rows_attempted == CCF_ROW_COUNT
    assert result.rows_inserted == CCF_ROW_COUNT - 5
    assert result.rows_skipped == 5


# ---------------------------------------------------------------------------
# insert_transactions — category_id passthrough
# ---------------------------------------------------------------------------


def test_insert_without_category_id_stores_null(
    conn: duckdb.DuckDBPyConnection, ccf_account: str
) -> None:
    df = parse_csv(CCF_FIXTURE, ccf_account, load_mapping("ccf_checking", TOML_CONFIG))
    insert_transactions(conn, df)
    null_count = _scalar(
        conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE category_id IS NULL"
        ).fetchone()
    )
    assert null_count == CCF_ROW_COUNT


def test_insert_with_category_id_preserves_value(
    conn: duckdb.DuckDBPyConnection, ccf_account: str
) -> None:
    df = parse_csv(CCF_FIXTURE, ccf_account, load_mapping("ccf_checking", TOML_CONFIG))
    salary_cat_id = str(
        _scalar(
            conn.execute(
                "SELECT id FROM categories WHERE name = 'Salary' AND direction = 'income'"
            ).fetchone()
        )
    )
    df_with_cat = df.with_columns(pl.lit(salary_cat_id).alias("category_id"))
    insert_transactions(conn, df_with_cat)
    count = _scalar(
        conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE category_id = ?",
            [salary_cat_id],
        ).fetchone()
    )
    assert count == CCF_ROW_COUNT


# ---------------------------------------------------------------------------
# load_mapping + parse_csv
# ---------------------------------------------------------------------------


def test_load_mapping_ccf(toml_config: Path = TOML_CONFIG) -> None:
    mapping = load_mapping("ccf_checking", toml_config)
    assert mapping.separator == ";"
    assert mapping.decimal_separator == ","
    assert mapping.date_format == "%d/%m/%Y"
    assert mapping.date_col == "Date operation"


def test_load_mapping_unknown_bank() -> None:
    with pytest.raises(KeyError, match="no_such_bank"):
        load_mapping("no_such_bank", TOML_CONFIG)


def test_parse_csv_produces_correct_schema() -> None:
    mapping = load_mapping("ccf_checking", TOML_CONFIG)
    df = parse_csv(CCF_FIXTURE, "dummy-account-id", mapping)
    assert df.columns == [
        "account_id",
        "date",
        "value_date",
        "amount",
        "description",
        "source",
        "import_hash",
    ]
    assert len(df) == CCF_ROW_COUNT


def test_parse_csv_livret_a(livret_a_account: str) -> None:
    mapping = load_mapping("ccf_livret_a", TOML_CONFIG)
    df = parse_csv(LIVRET_A_FIXTURE, livret_a_account, mapping)
    assert len(df) == LIVRET_A_ROW_COUNT
    # All hashes are unique
    assert df["import_hash"].n_unique() == LIVRET_A_ROW_COUNT


def test_import_two_accounts(
    conn: duckdb.DuckDBPyConnection,
    ccf_account: str,
    livret_a_account: str,
) -> None:
    ccf_df = parse_csv(
        CCF_FIXTURE, ccf_account, load_mapping("ccf_checking", TOML_CONFIG)
    )
    la_df = parse_csv(
        LIVRET_A_FIXTURE, livret_a_account, load_mapping("ccf_livret_a", TOML_CONFIG)
    )
    r1 = insert_transactions(conn, ccf_df)
    r2 = insert_transactions(conn, la_df)
    total = _scalar(conn.execute("SELECT COUNT(*) FROM transactions").fetchone())
    assert total == r1.rows_inserted + r2.rows_inserted
    assert total == CCF_ROW_COUNT + LIVRET_A_ROW_COUNT
