import duckdb


def initialise(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all tables if they don't exist.

    Called once at application startup. Safe to call multiple times —
    all DDL uses CREATE TABLE IF NOT EXISTS.

    Table creation order respects foreign key dependencies:
        accounts → categories → category_rules
        accounts + categories → transactions
        categories → budgets
        (savings_goals has no FK dependencies)

    After calling this, run ``seed_categories()`` from
    ``munger_matics.categories`` to populate the default system categories.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id              VARCHAR  NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
            name            VARCHAR  NOT NULL,
            type            VARCHAR  NOT NULL
                                CHECK (type IN (
                                    'checking', 'savings', 'investment',
                                    'retirement', 'credit_card', 'loan'
                                )),
            currency        VARCHAR  NOT NULL DEFAULT 'EUR',
            opening_balance DECIMAL(15, 2) NOT NULL DEFAULT 0,
            is_active       BOOLEAN  NOT NULL DEFAULT true,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id          VARCHAR  NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
            name        VARCHAR  NOT NULL,
            parent_id   VARCHAR  REFERENCES categories(id),
            direction   VARCHAR  NOT NULL
                            CHECK (direction IN ('income', 'expense', 'transfer')),
            sort_order  INTEGER  NOT NULL DEFAULT 0,
            created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS category_rules (
            id          VARCHAR  NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
            pattern     VARCHAR  NOT NULL,
            match_type  VARCHAR  NOT NULL
                            CHECK (match_type IN ('contains', 'starts_with', 'regex')),
            category_id VARCHAR  NOT NULL REFERENCES categories(id),
            priority    INTEGER  NOT NULL DEFAULT 100,
            amount_min  DECIMAL(15, 2),
            amount_max  DECIMAL(15, 2),
            created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id               VARCHAR  NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
            account_id       VARCHAR  NOT NULL REFERENCES accounts(id),
            date             DATE     NOT NULL,
            value_date       DATE,
            amount           DECIMAL(15, 2) NOT NULL,
            description      VARCHAR  NOT NULL,
            category_id      VARCHAR  REFERENCES categories(id),
            is_transfer      BOOLEAN  NOT NULL DEFAULT false,
            -- transfer_peer_id intentionally has no FK: DuckDB cannot enforce
            -- self-referential FKs in UPDATEs; integrity is upheld by
            -- mark_transfer() / confirm_transfer() in the application layer.
            transfer_peer_id VARCHAR,
            import_hash      VARCHAR  UNIQUE,
            source           VARCHAR  NOT NULL DEFAULT 'csv_import',
            created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id          VARCHAR  NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
            category_id VARCHAR  NOT NULL REFERENCES categories(id),
            month       DATE     NOT NULL,
            amount      DECIMAL(15, 2) NOT NULL,
            created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (category_id, month)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS savings_goals (
            id            VARCHAR  NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
            name          VARCHAR  NOT NULL,
            target_amount DECIMAL(15, 2) NOT NULL,
            target_date   DATE,
            created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
