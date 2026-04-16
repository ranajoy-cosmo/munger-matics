from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Generator

import duckdb
import pytest

from munger_matics.accounts import AccountType, add_account
from munger_matics.database.schema import initialise
from munger_matics.transactions import (
    confirm_transfer,
    detect_transfers,
    get_transaction,
    insert_transactions,
    load_mapping,
    parse_csv,
)
from munger_matics.transactions.transfers import TransferPair

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
def two_account_conn(conn: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """DB with CCF (15 rows) and Livret A (10 rows) imported."""
    ccf_id = add_account(conn, "CCF Checking", AccountType.CHECKING)
    la_id = add_account(conn, "Livret A", AccountType.SAVINGS)
    mapping = load_mapping("ccf_livret_a", TOML_CONFIG)
    insert_transactions(
        conn, parse_csv(CCF_FIXTURE, ccf_id, load_mapping("ccf_checking", TOML_CONFIG))
    )
    insert_transactions(conn, parse_csv(LIVRET_A_FIXTURE, la_id, mapping))
    return conn


def _scalar(row: tuple[object, ...] | None) -> object:
    assert row is not None
    return row[0]


# ---------------------------------------------------------------------------
# detect_transfers — fixture data
# ---------------------------------------------------------------------------


def test_detect_transfers_returns_list(
    two_account_conn: duckdb.DuckDBPyConnection,
) -> None:
    pairs = detect_transfers(two_account_conn)
    assert isinstance(pairs, list)


def test_detect_transfers_finds_known_pair(
    two_account_conn: duckdb.DuckDBPyConnection,
) -> None:
    # CCF row 13: 26/03/2026 +500.00 "VIR RECU LIVRET A VIREMENT"
    # Livret A row 7: 26/03/2026 -500.00 "VIR EMIS COMPTE CHEQUES VIREMENT"
    # These are opposite-sign, same-date, different accounts → candidate pair.
    pairs = detect_transfers(two_account_conn)
    amounts = {p.amount for p in pairs}
    assert Decimal("500.00") in amounts


def test_detect_transfers_returns_transfer_pair_type(
    two_account_conn: duckdb.DuckDBPyConnection,
) -> None:
    pairs = detect_transfers(two_account_conn)
    assert all(isinstance(p, TransferPair) for p in pairs)


def test_detect_transfers_pair_has_opposite_signs(
    two_account_conn: duckdb.DuckDBPyConnection,
) -> None:
    for p in detect_transfers(two_account_conn):
        assert (p.transaction_a.amount > 0) ^ (p.transaction_b.amount > 0), (
            "Transfer pair must have opposite-sign amounts"
        )


def test_detect_transfers_pair_different_accounts(
    two_account_conn: duckdb.DuckDBPyConnection,
) -> None:
    for p in detect_transfers(two_account_conn):
        assert p.transaction_a.account_id != p.transaction_b.account_id


def test_detect_transfers_earlier_date_is_a(
    two_account_conn: duckdb.DuckDBPyConnection,
) -> None:
    for p in detect_transfers(two_account_conn):
        assert p.transaction_a.date <= p.transaction_b.date


def test_detect_transfers_no_duplicates(
    two_account_conn: duckdb.DuckDBPyConnection,
) -> None:
    pairs = detect_transfers(two_account_conn)
    seen: set[frozenset[str]] = set()
    for p in pairs:
        key = frozenset({p.transaction_a.id, p.transaction_b.id})
        assert key not in seen, "Same pair returned more than once"
        seen.add(key)


def test_detect_transfers_already_marked_excluded(
    two_account_conn: duckdb.DuckDBPyConnection,
) -> None:
    # Confirm the known 500.00 pair, then detect_transfers should not return it again.
    pairs_before = detect_transfers(two_account_conn)
    pair_500 = next(p for p in pairs_before if p.amount == Decimal("500.00"))
    confirm_transfer(
        two_account_conn,
        pair_500.transaction_a.id,
        pair_500.transaction_b.id,
    )
    pairs_after = detect_transfers(two_account_conn)
    amounts_after = {p.amount for p in pairs_after}
    assert Decimal("500.00") not in amounts_after


# ---------------------------------------------------------------------------
# detect_transfers — window_days
# ---------------------------------------------------------------------------


def test_detect_transfers_window_zero_finds_same_day(
    two_account_conn: duckdb.DuckDBPyConnection,
) -> None:
    # The 500.00 pair is on the same day so window_days=0 must still find it.
    pairs = detect_transfers(two_account_conn, window_days=0)
    amounts = {p.amount for p in pairs}
    assert Decimal("500.00") in amounts


def test_detect_transfers_empty_db(conn: duckdb.DuckDBPyConnection) -> None:
    assert detect_transfers(conn) == []


def test_detect_transfers_single_account_no_pairs(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    ccf_id = add_account(conn, "CCF", AccountType.CHECKING)
    insert_transactions(
        conn, parse_csv(CCF_FIXTURE, ccf_id, load_mapping("ccf_checking", TOML_CONFIG))
    )
    # All transactions are on the same account — no cross-account pairs possible.
    pairs = detect_transfers(conn)
    assert pairs == []


# ---------------------------------------------------------------------------
# confirm_transfer
# ---------------------------------------------------------------------------


def test_confirm_transfer_sets_flags(
    two_account_conn: duckdb.DuckDBPyConnection,
) -> None:
    pairs = detect_transfers(two_account_conn)
    assert len(pairs) >= 1
    p = pairs[0]
    id_a = p.transaction_a.id
    id_b = p.transaction_b.id

    confirm_transfer(two_account_conn, id_a, id_b)

    ta = get_transaction(two_account_conn, id_a)
    tb = get_transaction(two_account_conn, id_b)
    assert ta.is_transfer is True
    assert ta.transfer_peer_id == id_b
    assert tb.is_transfer is True
    assert tb.transfer_peer_id == id_a


def test_confirm_transfer_unknown_transaction(
    two_account_conn: duckdb.DuckDBPyConnection,
) -> None:
    real_id = str(
        _scalar(
            two_account_conn.execute("SELECT id FROM transactions LIMIT 1").fetchone()
        )
    )
    with pytest.raises(KeyError, match="not found"):
        confirm_transfer(
            two_account_conn,
            real_id,
            "00000000-0000-0000-0000-000000000000",
        )


def test_confirm_transfer_already_transfer_raises(
    two_account_conn: duckdb.DuckDBPyConnection,
) -> None:
    pairs = detect_transfers(two_account_conn)
    p = pairs[0]
    id_a = p.transaction_a.id
    id_b = p.transaction_b.id

    confirm_transfer(two_account_conn, id_a, id_b)

    # A second confirm on either leg must raise ValueError, not silently overwrite.
    with pytest.raises(ValueError, match="already marked"):
        confirm_transfer(two_account_conn, id_a, id_b)
