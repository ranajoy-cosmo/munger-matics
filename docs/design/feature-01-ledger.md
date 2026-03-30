# Feature Spec: Phase 1 — Financial Ledger

This document is the implementation spec for Phase 1. It is the detailed, actionable reference for
each development session within Phase 1. The scope is defined in [Roadmap: Phase 1](roadmap.md).

---

## New Source Modules

```
src/munger_matics/
  database/
    schema.py           # UPDATED: add all Phase 1 DDL to initialise()
  accounts/
    __init__.py         # exports: Account, add_account, get_account, list_accounts, deactivate_account
    models.py           # Pydantic: Account, AccountCreate
    repository.py       # DuckDB CRUD
  transactions/
    __init__.py         # exports: Transaction, import_csv, add_transaction, list_transactions
    models.py           # Pydantic: Transaction, TransactionCreate
    repository.py       # bulk insert, list with filters, balance query
    import_csv.py       # CSV parse → TransactionCreate list, dedup hash generation
  categories/
    __init__.py         # exports: Category, add_category, list_categories, apply_rules
    models.py           # Pydantic: Category, CategoryCreate, CategoryRule, CategoryRuleCreate
    repository.py       # CRUD for categories and category_rules
    seed.py             # insert default hierarchy (idempotent)
    rules.py            # apply_rules(rows) → rows with category_id set
```

---

## New App Pages

```
app/pages/
  01_dashboard.py       # account balances, monthly income/expense, top-5 categories
  02_accounts.py        # add / edit / deactivate accounts
  03_import.py          # 3-step CSV import wizard
  04_transactions.py    # full ledger with filters and inline category editing
  05_categories.py      # manage categories and rules
```

`app/app.py` remains the entry point; update it to set `st.set_page_config` and add navigation.

---

## Database Schema Changes

Update `src/munger_matics/database/schema.py`:

```python
def initialise(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            name            VARCHAR      NOT NULL,
            type            VARCHAR      NOT NULL
                                CHECK (type IN ('checking','savings','investment',
                                                'retirement','credit_card','loan')),
            currency        VARCHAR(3)   NOT NULL DEFAULT 'EUR',
            institution     VARCHAR,
            opening_balance DECIMAL(15,2) NOT NULL DEFAULT 0,
            is_active       BOOLEAN      NOT NULL DEFAULT true,
            created_at      TIMESTAMP    NOT NULL DEFAULT now()
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id          UUID     PRIMARY KEY DEFAULT gen_random_uuid(),
            name        VARCHAR  NOT NULL,
            parent_id   UUID     REFERENCES categories(id),
            direction   VARCHAR  NOT NULL
                            CHECK (direction IN ('income','expense','transfer')),
            is_system   BOOLEAN  NOT NULL DEFAULT false,
            sort_order  INTEGER  NOT NULL DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id       UUID         NOT NULL REFERENCES accounts(id),
            date             DATE         NOT NULL,
            amount           DECIMAL(15,2) NOT NULL,
            description      VARCHAR      NOT NULL,
            raw_description  VARCHAR,
            merchant         VARCHAR,
            category_id      UUID         REFERENCES categories(id),
            notes            VARCHAR,
            is_transfer      BOOLEAN      NOT NULL DEFAULT false,
            transfer_peer_id UUID         REFERENCES transactions(id),
            source           VARCHAR      NOT NULL DEFAULT 'manual'
                                 CHECK (source IN ('manual','csv_import','api')),
            import_hash      VARCHAR      UNIQUE,
            created_at       TIMESTAMP    NOT NULL DEFAULT now()
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS category_rules (
            id          UUID     PRIMARY KEY DEFAULT gen_random_uuid(),
            pattern     VARCHAR  NOT NULL,
            match_type  VARCHAR  NOT NULL DEFAULT 'contains'
                            CHECK (match_type IN ('contains','starts_with','regex')),
            category_id UUID     NOT NULL REFERENCES categories(id),
            priority    INTEGER  NOT NULL DEFAULT 0,
            created_at  TIMESTAMP NOT NULL DEFAULT now()
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            category_id UUID         NOT NULL REFERENCES categories(id),
            month       DATE         NOT NULL,
            amount      DECIMAL(15,2) NOT NULL CHECK (amount > 0),
            created_at  TIMESTAMP    NOT NULL DEFAULT now(),
            UNIQUE (category_id, month)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS savings_goals (
            id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            name            VARCHAR      NOT NULL,
            target_amount   DECIMAL(15,2) NOT NULL CHECK (target_amount > 0),
            current_amount  DECIMAL(15,2) NOT NULL DEFAULT 0,
            target_date     DATE,
            notes           VARCHAR,
            is_achieved     BOOLEAN      NOT NULL DEFAULT false,
            created_at      TIMESTAMP    NOT NULL DEFAULT now()
        )
    """)
```

---

## CSV Import Design

### Column Mapping Config

Institution-specific column mappings are stored in `config/csv_mappings.toml`:

```toml
[ing]
date = "Date"
amount = "Amount"
description = "Description"
date_format = "%d/%m/%Y"
decimal_separator = ","
thousands_separator = "."

[n26]
date = "Date"
amount = "Amount (EUR)"
description = "Payee"
date_format = "%Y-%m-%d"
decimal_separator = "."
```

A "generic" mapping is attempted as a fallback when no institution is selected.

### Import Wizard (3 steps)

**Step 1 — Upload**
- `st.file_uploader` accepting `.csv`
- Auto-detect delimiter (comma or semicolon) and encoding (UTF-8 or Latin-1)
- Show raw preview (first 5 rows)
- Institution selector dropdown (populated from `config/csv_mappings.toml` keys + "Generic")

**Step 2 — Map Columns**
- If institution is known: pre-fill column mapping from config and allow override
- If generic: show dropdowns for (date column, amount column, description column)
- Date format input (pre-filled per institution)
- Show parsed preview (5 rows in standard format) with types applied

**Step 3 — Review & Confirm**
- Parse all rows
- Show: N total rows, M duplicates that will be skipped, K new rows to import
- Apply category rules to new rows; show predicted categories
- "Confirm import" button → bulk insert → success message with import count

### Deduplication

Hash is computed as:

```python
import hashlib
from decimal import Decimal

def make_import_hash(account_id: str, date: str, amount: Decimal, raw_description: str) -> str:
    payload = f"{account_id}|{date}|{amount}|{raw_description}"
    return hashlib.sha256(payload.encode()).hexdigest()
```

On bulk insert, rows with a hash already present in the `import_hash` column are skipped silently.

---

## Category Rules Engine

Rules are applied in order of descending `priority`, then descending `created_at`. The first
matching rule wins.

```python
# categories/rules.py

def apply_rules(
    rows: list[TransactionCreate],
    rules: list[CategoryRule],
) -> list[TransactionCreate]:
    """
    Assign category_id to each row where it is None.
    Rows that already have a category_id are not modified.
    Returns the same list with category_ids populated where rules matched.
    """
```

Match types:

| Type | Behaviour |
|---|---|
| `contains` | `pattern.lower() in raw_description.lower()` |
| `starts_with` | `raw_description.lower().startswith(pattern.lower())` |
| `regex` | `re.search(pattern, raw_description, re.IGNORECASE)` |

---

## Transfer Detection

Run after import (or on demand from the transactions page):

```python
# transactions/repository.py

def detect_transfers(conn, account_ids: list[str], window_days: int = 2) -> int:
    """
    Identify transaction pairs that are inter-account transfers.
    Criteria:
      - amount on one row equals -amount on the other
      - both belong to accounts in account_ids
      - dates are within window_days of each other
      - neither is already flagged as a transfer

    Updates both rows: is_transfer=true, transfer_peer_id=each other's id.
    Returns number of pairs detected.
    """
```

---

## Key Implementation Constraints

| Constraint | Detail |
|---|---|
| `Decimal` everywhere | Import `from decimal import Decimal`. Never cast amounts to `float`. |
| No `float` in schema | DuckDB column type is `DECIMAL(15,2)`. Python type is `Decimal`. |
| Pydantic boundary | All data crossing from DB to app logic goes through a Pydantic model. |
| `app/` is dumb | App pages call repository functions. Zero calculation logic in `app/`. |
| Idempotent schema | `CREATE TABLE IF NOT EXISTS` — `initialise()` is safe to call multiple times. |
| Idempotent seed | `seed.py` checks for existing system categories before inserting. |

---

## Test Plan

Each sub-module requires tests in the mirrored `tests/` path.

### `tests/database/test_schema.py`
- `test_initialise_creates_all_tables` — run `initialise()`, assert all 6 tables exist
- `test_initialise_is_idempotent` — run `initialise()` twice, no error, same tables

### `tests/accounts/test_repository.py`
- `test_add_account_returns_id`
- `test_list_accounts_excludes_inactive`
- `test_balance_calculation` — opening_balance=100, two transactions (+50, -30) → balance=120
- `test_deactivate_does_not_delete`

### `tests/transactions/test_import_csv.py`
- `test_parse_ing_csv` — parse a known fixture, assert correct date/amount/description
- `test_parse_n26_csv` — same for N26 format
- `test_dedup_hash_is_stable` — same inputs produce same hash
- `test_duplicate_detection` — import same rows twice, second import inserts 0 rows
- `test_negative_amount_is_debit` — amount column "-50.00" → Decimal("-50.00")

### `tests/transactions/test_repository.py`
- `test_bulk_insert`
- `test_list_filter_by_account`
- `test_list_filter_by_date_range`
- `test_list_filter_by_category`
- `test_transfer_detection` — two matching rows → both flagged, linked

### `tests/categories/test_rules.py`
- `test_contains_rule_matches`
- `test_starts_with_rule_matches`
- `test_regex_rule_matches`
- `test_priority_order` — two matching rules, higher priority wins
- `test_existing_category_not_overwritten` — rows with a category_id are left unchanged

### `tests/categories/test_seed.py`
- `test_seed_inserts_all_system_categories`
- `test_seed_is_idempotent` — run twice, same row count

---

## Dashboard Queries

The dashboard is driven by two queries (both executed via `get_connection()`):

**Account balances:**
```sql
SELECT
    a.name,
    a.type,
    a.currency,
    a.opening_balance + COALESCE(SUM(t.amount), 0) AS balance
FROM accounts a
LEFT JOIN transactions t ON t.account_id = a.id AND t.is_transfer = false
WHERE a.is_active = true
GROUP BY a.id, a.name, a.type, a.currency, a.opening_balance
ORDER BY a.type, a.name;
```

**Monthly income / expenses by category:**
```sql
SELECT
    c.name                  AS category,
    SUM(t.amount)           AS total,
    c.direction
FROM transactions t
JOIN categories c ON c.id = t.category_id
WHERE t.date >= :month_start
  AND t.date <  :month_end
  AND t.is_transfer = false
GROUP BY c.id, c.name, c.direction
ORDER BY ABS(SUM(t.amount)) DESC;
```

`:month_start` and `:month_end` are parameterised — never string-interpolated.

---

## Configuration Files to Create

`config/csv_mappings.toml` — institution column mapping presets (committed to git)

`config/categories.toml` — seed category definitions (committed to git, used by `seed.py`)
