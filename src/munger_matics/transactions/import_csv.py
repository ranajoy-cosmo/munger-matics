from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

import duckdb
import polars as pl
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# InsertResult — returned by insert_transactions
# ---------------------------------------------------------------------------


class InsertResult(BaseModel):
    rows_attempted: int
    rows_inserted: int
    rows_skipped: int


# ---------------------------------------------------------------------------
# CsvMapping — generic bank CSV format descriptor
# ---------------------------------------------------------------------------


@dataclass
class CsvMapping:
    separator: str
    date_format: str
    date_col: str
    value_date_col: str
    description_col: str
    debit_col: str
    credit_col: str
    decimal_separator: str


def load_mapping(bank_name: str, config_path: Path) -> CsvMapping:
    """Load a bank's CSV mapping from a TOML config file.

    Args:
        bank_name:   Key inside the TOML file, e.g. ``"ccf_checking"`` or ``"ccf_livret_a"``.
        config_path: Absolute path to the TOML file (typically
                     ``project_root / "config" / "csv_mappings.toml"``).

    Raises:
        KeyError: if bank_name is not a section in the config file.
    """
    with config_path.open("rb") as f:
        data = tomllib.load(f)
    if bank_name not in data:
        raise KeyError(f"No CSV mapping defined for bank {bank_name!r}")
    raw = data[bank_name]
    return CsvMapping(
        separator=raw["separator"],
        date_format=raw["date_format"],
        date_col=raw["date_col"],
        value_date_col=raw["value_date_col"],
        description_col=raw["description_col"],
        debit_col=raw["debit_col"],
        credit_col=raw["credit_col"],
        decimal_separator=raw["decimal_separator"],
    )


# ---------------------------------------------------------------------------
# Generic CSV parser — bank-agnostic, driven by CsvMapping
# ---------------------------------------------------------------------------


def parse_csv(path: Path, account_id: str, mapping: CsvMapping) -> pl.DataFrame:
    """Parse any bank CSV export using the supplied column mapping.

    Produces the same 7-column schema as all bank parsers so that the rest
    of the pipeline is bank-agnostic.  Use ``load_mapping`` to obtain a
    ``CsvMapping`` from ``config/csv_mappings.toml``.

    The dedup hash covers the same payload as ``parse_ccf_csv``:
        account_id | row_position | date_col | debit_col | credit_col | description_col
    """
    raw = pl.read_csv(path, separator=mapping.separator, infer_schema=False)

    # Strip BOM from the first column name (common in French bank exports).
    raw = raw.rename({c: c.lstrip("\ufeff") for c in raw.columns})

    raw = raw.with_row_index("_row_idx")

    import_hashes = (
        pl.concat_str(
            [
                pl.lit(account_id),
                pl.col("_row_idx").cast(pl.String),
                pl.col(mapping.date_col),
                pl.col(mapping.debit_col),
                pl.col(mapping.credit_col),
                pl.col(mapping.description_col),
            ],
            separator="|",
        )
        .map_elements(
            lambda s: hashlib.sha256(s.encode()).hexdigest(),
            return_dtype=pl.String,
        )
        .alias("import_hash")
    )

    debit = (
        pl.col(mapping.debit_col)
        .str.replace(mapping.decimal_separator, ".", literal=True)
        .cast(pl.Decimal(scale=2), strict=False)
        .neg()
    )
    credit = (
        pl.col(mapping.credit_col)
        .str.replace(mapping.decimal_separator, ".", literal=True)
        .cast(pl.Decimal(scale=2), strict=False)
    )

    return (
        raw.with_columns(import_hashes)
        .with_columns(
            pl.col(mapping.date_col)
            .str.strptime(pl.Date, mapping.date_format)
            .alias("date"),
            pl.col(mapping.value_date_col)
            .str.strptime(pl.Date, mapping.date_format)
            .alias("value_date"),
            debit.alias("_debit"),
            credit.alias("_credit"),
            pl.col(mapping.description_col).alias("description"),
            pl.lit(account_id).alias("account_id"),
            pl.lit("csv_import").alias("source"),
        )
        .with_columns(pl.coalesce(["_debit", "_credit"]).alias("amount"))
        .select(
            [
                "account_id",
                "date",
                "value_date",
                "amount",
                "description",
                "source",
                "import_hash",
            ]
        )
    )


# ---------------------------------------------------------------------------
# DB insert — idempotent, deduplicates on import_hash
# ---------------------------------------------------------------------------


def insert_transactions(
    conn: duckdb.DuckDBPyConnection, df: pl.DataFrame
) -> InsertResult:
    """Insert a parsed transaction DataFrame into the ``transactions`` table.

    Duplicate rows (matched by ``import_hash``) are silently skipped so the
    same CSV can be re-imported without creating duplicates.

    If the DataFrame contains a ``category_id`` column (e.g. after calling
    ``apply_rules``), it is included in the insert.  Otherwise ``category_id``
    defaults to NULL.

    Returns:
        ``InsertResult`` with ``rows_attempted``, ``rows_inserted``,
        ``rows_skipped``.
    """
    rows_attempted = len(df)

    # Ensure category_id column exists so the INSERT statement is uniform.
    if "category_id" not in df.columns:
        df = df.with_columns(pl.lit(None).cast(pl.String).alias("category_id"))

    conn.register("_import_df", df)
    try:
        returning = conn.execute("""
            INSERT INTO transactions
                (account_id, date, value_date, amount, description,
                 source, import_hash, category_id)
            SELECT
                account_id, date, value_date, amount::DECIMAL(15,2), description,
                source, import_hash, category_id
            FROM _import_df
            ON CONFLICT (import_hash) DO NOTHING
            RETURNING id
        """).fetchall()
    finally:
        conn.unregister("_import_df")

    rows_inserted = len(returning)
    return InsertResult(
        rows_attempted=rows_attempted,
        rows_inserted=rows_inserted,
        rows_skipped=rows_attempted - rows_inserted,
    )
