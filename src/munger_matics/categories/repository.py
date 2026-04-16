from __future__ import annotations

import tomllib
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import BaseModel


class Direction(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class MatchType(StrEnum):
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    REGEX = "regex"


class Category(BaseModel):
    id: str
    name: str
    parent_id: str | None
    direction: Direction
    sort_order: int
    created_at: datetime


class CategoryRule(BaseModel):
    id: str
    pattern: str
    match_type: MatchType
    category_id: str
    priority: int
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Repository functions — categories
# ---------------------------------------------------------------------------


def list_categories(
    conn: duckdb.DuckDBPyConnection,
    *,
    direction: Direction | Literal["income", "expense", "transfer"] | None = None,
) -> list[Category]:
    """Return all categories, optionally filtered by direction.

    Ordered by direction then sort_order so the result is stable and
    predictable for UI rendering.
    """
    query = """
        SELECT id, name, parent_id, direction, sort_order, created_at
        FROM categories
    """
    if direction is not None:
        query += f" WHERE direction = '{direction}'"
    query += " ORDER BY direction, sort_order, name"

    return [
        Category(
            id=r[0],
            name=r[1],
            parent_id=r[2],
            direction=r[3],
            sort_order=r[4],
            created_at=r[5],
        )
        for r in conn.execute(query).fetchall()
    ]


def get_category(conn: duckdb.DuckDBPyConnection, category_id: str) -> Category:
    """Return a Category by ID. Raises KeyError if not found."""
    row = conn.execute(
        """
        SELECT id, name, parent_id, direction, sort_order, created_at
        FROM categories
        WHERE id = ?
        """,
        [category_id],
    ).fetchone()
    if row is None:
        raise KeyError(f"Category not found: {category_id!r}")
    return Category(
        id=row[0],
        name=row[1],
        parent_id=row[2],
        direction=row[3],
        sort_order=row[4],
        created_at=row[5],
    )


def add_category(
    conn: duckdb.DuckDBPyConnection,
    name: str,
    direction: Direction | Literal["income", "expense", "transfer"],
    *,
    parent_id: str | None = None,
    sort_order: int = 0,
) -> str:
    """Insert a new user category and return its generated UUID.

    Raises KeyError if parent_id is provided but does not exist.
    """
    if parent_id is not None:
        exists = conn.execute(
            "SELECT 1 FROM categories WHERE id = ?", [parent_id]
        ).fetchone()
        if exists is None:
            raise KeyError(f"Parent category not found: {parent_id!r}")

    row = conn.execute(
        """
        INSERT INTO categories (name, direction, parent_id, sort_order)
        VALUES (?, ?, ?, ?)
        RETURNING id
        """,
        [name, str(direction), parent_id, sort_order],
    ).fetchone()
    assert row is not None
    return str(row[0])


# ---------------------------------------------------------------------------
# Repository functions — category rules
# ---------------------------------------------------------------------------


def add_rule(
    conn: duckdb.DuckDBPyConnection,
    pattern: str,
    match_type: MatchType | Literal["contains", "starts_with", "regex"],
    category_id: str,
    *,
    priority: int = 100,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
) -> str:
    """Insert a category rule and return its generated UUID.

    Raises KeyError if category_id does not exist.
    """
    exists = conn.execute(
        "SELECT 1 FROM categories WHERE id = ?", [category_id]
    ).fetchone()
    if exists is None:
        raise KeyError(f"Category not found: {category_id!r}")

    row = conn.execute(
        """
        INSERT INTO category_rules (pattern, match_type, category_id, priority, amount_min, amount_max)
        VALUES (?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        [pattern, str(match_type), category_id, priority, amount_min, amount_max],
    ).fetchone()
    assert row is not None
    return str(row[0])


def list_rules(
    conn: duckdb.DuckDBPyConnection,
    *,
    category_id: str | None = None,
) -> list[CategoryRule]:
    """Return all category rules ordered by priority (ascending).

    Optionally filter to rules belonging to a single category.
    """
    query = """
        SELECT id, pattern, match_type, category_id, priority, amount_min, amount_max, created_at
        FROM category_rules
    """
    if category_id is not None:
        query += f" WHERE category_id = '{category_id}'"
    query += " ORDER BY priority, created_at"

    return [
        CategoryRule(
            id=r[0],
            pattern=r[1],
            match_type=r[2],
            category_id=r[3],
            priority=r[4],
            amount_min=r[5],
            amount_max=r[6],
            created_at=r[7],
        )
        for r in conn.execute(query).fetchall()
    ]


def delete_rule(conn: duckdb.DuckDBPyConnection, rule_id: str) -> None:
    """Delete a category rule by ID. Raises KeyError if not found."""
    exists = conn.execute(
        "SELECT 1 FROM category_rules WHERE id = ?", [rule_id]
    ).fetchone()
    if exists is None:
        raise KeyError(f"Category rule not found: {rule_id!r}")
    conn.execute("DELETE FROM category_rules WHERE id = ?", [rule_id])


# ---------------------------------------------------------------------------
# Category seed
# ---------------------------------------------------------------------------


def seed_categories(conn: duckdb.DuckDBPyConnection, config_path: Path) -> None:
    """Seed default system categories from a TOML config file.

    Idempotent: categories whose (name, direction) pair already exists in the
    database are skipped, so this is safe to call multiple times.

    Args:
        conn:        Active DuckDB connection with the schema already initialised.
        config_path: Path to a TOML file whose top-level keys are direction
                     strings (``income``, ``expense``, ``transfer``) and whose
                     values are arrays of ``{name, sort_order}`` entries.

    Raises:
        KeyError: if config_path does not exist or is missing expected keys.
    """
    with config_path.open("rb") as f:
        data = tomllib.load(f)

    existing = {
        (row[0], row[1])
        for row in conn.execute("SELECT name, direction FROM categories").fetchall()
    }

    rows: list[tuple[str, str, int]] = [
        (entry["name"], direction, entry["sort_order"])
        for direction, entries in data.items()
        for entry in entries
        if (entry["name"], direction) not in existing
    ]

    if rows:
        conn.executemany(
            """
            INSERT INTO categories (name, direction, sort_order)
            VALUES (?, ?, ?)
            """,
            rows,
        )
