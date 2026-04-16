"""Tests for the categories repository."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from munger_matics.categories.repository import (
    Category,
    CategoryRule,
    Direction,
    MatchType,
    add_category,
    add_rule,
    delete_rule,
    get_category,
    list_categories,
    list_rules,
    seed_categories,
)
from munger_matics.database.schema import initialise

CATEGORIES_CONFIG = (
    Path(__file__).parent.parent.parent / "config" / "default_categories.toml"
)


@pytest.fixture
def db() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    initialise(conn)
    seed_categories(conn, CATEGORIES_CONFIG)
    return conn


def _groceries_id(conn: duckdb.DuckDBPyConnection) -> str:
    row = conn.execute("SELECT id FROM categories WHERE name = 'Groceries'").fetchone()
    assert row is not None
    return str(row[0])


# ---------------------------------------------------------------------------
# list_categories
# ---------------------------------------------------------------------------


def test_list_categories_returns_all_seeded(db: duckdb.DuckDBPyConnection) -> None:
    categories = list_categories(db)
    assert len(categories) == 20


def test_list_categories_filtered_by_direction(db: duckdb.DuckDBPyConnection) -> None:
    income = list_categories(db, direction=Direction.INCOME)
    assert len(income) == 5
    assert all(c.direction == Direction.INCOME for c in income)


def test_list_categories_filtered_by_string_direction(
    db: duckdb.DuckDBPyConnection,
) -> None:
    expense = list_categories(db, direction="expense")
    assert len(expense) == 13


def test_list_categories_ordered_by_sort_order(db: duckdb.DuckDBPyConnection) -> None:
    income = list_categories(db, direction=Direction.INCOME)
    orders = [c.sort_order for c in income]
    assert orders == sorted(orders)


def test_list_categories_returns_category_models(db: duckdb.DuckDBPyConnection) -> None:
    categories = list_categories(db)
    assert all(isinstance(c, Category) for c in categories)


def test_list_categories_includes_user_categories(
    db: duckdb.DuckDBPyConnection,
) -> None:
    add_category(db, "Pet Care", Direction.EXPENSE)
    all_cats = list_categories(db)
    names = [c.name for c in all_cats]
    assert "Pet Care" in names


# ---------------------------------------------------------------------------
# get_category
# ---------------------------------------------------------------------------


def test_get_category_raises_for_unknown_id(db: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(KeyError, match="no-such-id"):
        get_category(db, "no-such-id")


def test_get_category_returns_category_model(db: duckdb.DuckDBPyConnection) -> None:
    cat_id = _groceries_id(db)
    category = get_category(db, cat_id)
    assert isinstance(category, Category)
    assert category.name == "Groceries"
    assert category.direction == Direction.EXPENSE


# ---------------------------------------------------------------------------
# add_category
# ---------------------------------------------------------------------------


def test_add_category_returns_uuid(db: duckdb.DuckDBPyConnection) -> None:
    cat_id = add_category(db, "Pet Care", Direction.EXPENSE)
    assert isinstance(cat_id, str)
    assert len(cat_id) == 36


def test_add_category_stored_correctly(db: duckdb.DuckDBPyConnection) -> None:
    cat_id = add_category(db, "Freelance", Direction.INCOME, sort_order=50)
    category = get_category(db, cat_id)
    assert category.name == "Freelance"
    assert category.direction == Direction.INCOME
    assert category.sort_order == 50
    assert category.parent_id is None


def test_add_category_with_parent(db: duckdb.DuckDBPyConnection) -> None:
    parent_id = add_category(db, "Food", Direction.EXPENSE)
    child_id = add_category(db, "Organic", Direction.EXPENSE, parent_id=parent_id)
    child = get_category(db, child_id)
    assert child.parent_id == parent_id


def test_add_category_raises_for_nonexistent_parent(
    db: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(KeyError, match="no-such-parent"):
        add_category(db, "Sub", Direction.EXPENSE, parent_id="no-such-parent")


def test_add_category_accepts_string_direction(db: duckdb.DuckDBPyConnection) -> None:
    cat_id = add_category(db, "Reimbursement", "income")
    category = get_category(db, cat_id)
    assert category.direction == Direction.INCOME


# ---------------------------------------------------------------------------
# add_rule
# ---------------------------------------------------------------------------


def test_add_rule_returns_uuid(db: duckdb.DuckDBPyConnection) -> None:
    cat_id = _groceries_id(db)
    rule_id = add_rule(db, "GRAND FRAIS", MatchType.CONTAINS, cat_id)
    assert isinstance(rule_id, str)
    assert len(rule_id) == 36


def test_add_rule_stored_correctly(db: duckdb.DuckDBPyConnection) -> None:
    cat_id = _groceries_id(db)
    rule_id = add_rule(db, "GRAND FRAIS", MatchType.CONTAINS, cat_id, priority=10)
    rules = list_rules(db)
    rule = next(r for r in rules if r.id == rule_id)
    assert rule.pattern == "GRAND FRAIS"
    assert rule.match_type == MatchType.CONTAINS
    assert rule.category_id == cat_id
    assert rule.priority == 10


def test_add_rule_default_priority(db: duckdb.DuckDBPyConnection) -> None:
    cat_id = _groceries_id(db)
    rule_id = add_rule(db, "ALDI", MatchType.STARTS_WITH, cat_id)
    rules = list_rules(db)
    rule = next(r for r in rules if r.id == rule_id)
    assert rule.priority == 100


def test_add_rule_raises_for_unknown_category(db: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(KeyError, match="no-such-cat"):
        add_rule(db, "ALDI", MatchType.CONTAINS, "no-such-cat")


def test_add_rule_accepts_string_match_type(db: duckdb.DuckDBPyConnection) -> None:
    cat_id = _groceries_id(db)
    rule_id = add_rule(db, "^PREL", "regex", cat_id)
    rule = next(r for r in list_rules(db) if r.id == rule_id)
    assert rule.match_type == MatchType.REGEX


# ---------------------------------------------------------------------------
# list_rules
# ---------------------------------------------------------------------------


def test_list_rules_empty_initially(db: duckdb.DuckDBPyConnection) -> None:
    assert list_rules(db) == []


def test_list_rules_ordered_by_priority(db: duckdb.DuckDBPyConnection) -> None:
    cat_id = _groceries_id(db)
    add_rule(db, "CARREFOUR", MatchType.CONTAINS, cat_id, priority=50)
    add_rule(db, "GRAND FRAIS", MatchType.CONTAINS, cat_id, priority=10)
    add_rule(db, "ALDI", MatchType.STARTS_WITH, cat_id, priority=30)
    rules = list_rules(db)
    priorities = [r.priority for r in rules]
    assert priorities == sorted(priorities)


def test_list_rules_filtered_by_category(db: duckdb.DuckDBPyConnection) -> None:
    groceries_id = _groceries_id(db)
    row = db.execute("SELECT id FROM categories WHERE name = 'Dining Out'").fetchone()
    assert row is not None
    dining_id = str(row[0])

    add_rule(db, "GRAND FRAIS", MatchType.CONTAINS, groceries_id)
    add_rule(db, "LE ZINC", MatchType.CONTAINS, dining_id)

    groceries_rules = list_rules(db, category_id=groceries_id)
    assert len(groceries_rules) == 1
    assert groceries_rules[0].pattern == "GRAND FRAIS"


def test_list_rules_returns_rule_models(db: duckdb.DuckDBPyConnection) -> None:
    cat_id = _groceries_id(db)
    add_rule(db, "ALDI", MatchType.CONTAINS, cat_id)
    rules = list_rules(db)
    assert all(isinstance(r, CategoryRule) for r in rules)


# ---------------------------------------------------------------------------
# delete_rule
# ---------------------------------------------------------------------------


def test_delete_rule_removes_it(db: duckdb.DuckDBPyConnection) -> None:
    cat_id = _groceries_id(db)
    rule_id = add_rule(db, "ALDI", MatchType.CONTAINS, cat_id)
    assert len(list_rules(db)) == 1
    delete_rule(db, rule_id)
    assert len(list_rules(db)) == 0


def test_delete_rule_raises_for_unknown_id(db: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(KeyError, match="no-such-rule"):
        delete_rule(db, "no-such-rule")


def test_delete_rule_only_removes_target(db: duckdb.DuckDBPyConnection) -> None:
    cat_id = _groceries_id(db)
    rule_a = add_rule(db, "ALDI", MatchType.CONTAINS, cat_id, priority=10)
    rule_b = add_rule(db, "LECLERC", MatchType.CONTAINS, cat_id, priority=20)
    delete_rule(db, rule_a)
    remaining = list_rules(db)
    assert len(remaining) == 1
    assert remaining[0].id == rule_b
