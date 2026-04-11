from __future__ import annotations

import hashlib
from pathlib import Path

import polars as pl

_DATE_FORMAT = "%d/%m/%Y"


def parse_ccf_csv(path: Path, account_id: str) -> pl.DataFrame:
    """Parse a CCF (Crédit Commercial de France) CSV export and return a clean ledger DataFrame.

    CCF CSV format — semicolon-delimited, quoted fields, UTF-8 (possibly with BOM):
        "Date operation";"Date valeur";"Libelle";"Debit";"Credit"

    Amounts use French decimal notation (comma as separator, e.g. "23,95").
    Exactly one of Debit/Credit is populated per row.
    Debit is a positive number representing money leaving the account.
    Credit is a positive number representing money entering the account.

    All bank-specific parse functions in this module return the same DataFrame schema
    so that the rest of the pipeline is bank-agnostic.

    The import_hash is computed from raw strings before any type conversion so
    that it remains stable across re-imports even if parsing logic changes.
    Row position within the file is included in the payload so that two
    legitimately identical transactions (same day, amount, merchant) are not
    collapsed into one — re-importing the same file produces the same positions
    and therefore the same hashes, so the DB UNIQUE constraint still prevents
    double-import.
    Hash payload: account_id|row_position|Date operation|Debit|Credit|Libelle

    Args:
        path: Path to the raw CSV file.
        account_id: UUID string of the account this file belongs to.

    Returns:
        DataFrame with columns:
            account_id   String
            date         Date    booking date ("Date operation")
            value_date   Date    value date   ("Date valeur")
            amount       Decimal(scale=2)  negative=debit, positive=credit
            description  String  raw Libelle
            source       String  always 'csv_import'
            import_hash  String  SHA-256 dedup key
    """
    raw = pl.read_csv(path, separator=";", infer_schema=False)

    # Strip BOM from column names — some French bank exports include a UTF-8 BOM
    # which attaches invisibly to the first column name.
    raw = raw.rename({c: c.lstrip("\ufeff") for c in raw.columns})

    # Add a stable row index. This is included in the hash so that two legitimately
    # identical transactions in the same file (same date, amount, description) get
    # distinct hashes. Re-importing the same file produces the same row positions,
    # so the DB UNIQUE constraint still prevents double-import.
    raw = raw.with_row_index("_row_idx")

    # Compute hash from raw strings before any transformation.
    import_hashes = (
        pl.concat_str(
            [
                pl.lit(account_id),
                pl.col("_row_idx").cast(pl.String),
                pl.col("Date operation"),
                pl.col("Debit"),
                pl.col("Credit"),
                pl.col("Libelle"),
            ],
            separator="|",
        )
        .map_elements(
            lambda s: hashlib.sha256(s.encode()).hexdigest(),
            return_dtype=pl.String,
        )
        .alias("import_hash")
    )

    # Parse amounts: replace French decimal comma with dot, then cast to Decimal.
    # strict=False means empty strings cast to null rather than raising an error.
    # Debit is negated (money leaving the account); null.neg() stays null.
    # Exactly one of the two columns is non-empty per row; coalesce picks it.
    debit = (
        pl.col("Debit")
        .str.replace(",", ".")
        .cast(pl.Decimal(scale=2), strict=False)
        .neg()
    )
    credit = (
        pl.col("Credit").str.replace(",", ".").cast(pl.Decimal(scale=2), strict=False)
    )

    return (
        raw.with_columns(import_hashes)
        .with_columns(
            pl.col("Date operation").str.strptime(pl.Date, _DATE_FORMAT).alias("date"),
            pl.col("Date valeur")
            .str.strptime(pl.Date, _DATE_FORMAT)
            .alias("value_date"),
            debit.alias("_debit"),
            credit.alias("_credit"),
            pl.col("Libelle").alias("description"),
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
