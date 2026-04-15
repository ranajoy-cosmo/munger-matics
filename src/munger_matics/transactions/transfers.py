from __future__ import annotations

from decimal import Decimal

import duckdb
from pydantic import BaseModel

from munger_matics.transactions.repository import Transaction, _row_to_transaction


# ---------------------------------------------------------------------------
# TransferPair model
# ---------------------------------------------------------------------------


class TransferPair(BaseModel):
    """A candidate transfer pair identified by ``detect_transfers``.

    Both transactions are included in full so callers can display all
    relevant details before asking the user for confirmation.

    ``amount_a`` and ``amount_b`` sum to approximately zero (opposite signs).
    """

    transaction_a: Transaction
    transaction_b: Transaction

    @property
    def amount(self) -> Decimal:
        """The absolute value of the transfer amount."""
        return abs(self.transaction_a.amount)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

_SELECT_CANDIDATE = """
    SELECT
        id, account_id, date, value_date, amount, description,
        category_id, is_transfer, transfer_peer_id, import_hash, source, created_at
    FROM transactions
    WHERE is_transfer = false
"""


def detect_transfers(
    conn: duckdb.DuckDBPyConnection,
    *,
    window_days: int = 3,
    amount_tolerance: Decimal = Decimal("0.00"),
) -> list[TransferPair]:
    """Find candidate transfer pairs across accounts.

    A candidate pair is two transactions where:
    - They belong to **different** accounts
    - The amounts are opposite in sign: one positive, one negative
    - |amount_a| and |amount_b| differ by at most ``amount_tolerance``
    - Their booking dates differ by at most ``window_days``
    - Neither transaction is already marked as a transfer

    Returns advisory candidates only.  The user must call
    ``confirm_transfer`` to actually link a pair.

    Each pair is returned once: transaction_a has the earlier (or equal) date.
    """
    rows_a = conn.execute(_SELECT_CANDIDATE).fetchall()
    transactions = [_row_to_transaction(r) for r in rows_a]

    # Filter to only those with a non-zero amount (skip zero-amount anomalies).
    candidates = [t for t in transactions if t.amount != Decimal("0")]

    pairs: list[TransferPair] = []
    seen: set[tuple[str, str]] = set()

    for i, ta in enumerate(candidates):
        for tb in candidates[i + 1 :]:
            # Must be different accounts.
            if ta.account_id == tb.account_id:
                continue
            # Must have opposite signs.
            if not ((ta.amount > 0) ^ (tb.amount > 0)):
                continue
            # Amount magnitudes must be within tolerance.
            if abs(abs(ta.amount) - abs(tb.amount)) > amount_tolerance:
                continue
            # Dates must be within window.
            delta_days = abs((ta.date - tb.date).days)
            if delta_days > window_days:
                continue

            # Order so that the earlier-dated transaction is always 'a'.
            first, second = (ta, tb) if ta.date <= tb.date else (tb, ta)
            key = (first.id, second.id)
            if key in seen:
                continue
            seen.add(key)
            pairs.append(TransferPair(transaction_a=first, transaction_b=second))

    return pairs


# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------


def confirm_transfer(
    conn: duckdb.DuckDBPyConnection,
    transaction_id_a: str,
    transaction_id_b: str,
) -> None:
    """Mark two transactions as a confirmed transfer pair.

    Sets ``is_transfer = true`` and links ``transfer_peer_id`` on both rows.
    Raises KeyError if either transaction does not exist or if either is
    already marked as a transfer.
    """
    for tid in (transaction_id_a, transaction_id_b):
        row = conn.execute(
            "SELECT is_transfer FROM transactions WHERE id = ?", [tid]
        ).fetchone()
        if row is None:
            raise KeyError(f"Transaction not found: {tid!r}")
        if row[0]:
            raise ValueError(f"Transaction {tid!r} is already marked as a transfer")

    # Use a single UPDATE to avoid DuckDB's self-FK constraint error
    # that occurs when two rows reference each other in sequential UPDATEs.
    conn.execute(
        """
        UPDATE transactions
        SET is_transfer = true,
            transfer_peer_id = CASE WHEN id = ? THEN ? WHEN id = ? THEN ? END
        WHERE id IN (?, ?)
        """,
        [
            transaction_id_a,
            transaction_id_b,
            transaction_id_b,
            transaction_id_a,
            transaction_id_a,
            transaction_id_b,
        ],
    )
