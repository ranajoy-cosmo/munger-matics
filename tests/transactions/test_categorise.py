from __future__ import annotations

from datetime import date

import polars as pl

from munger_matics.categories.repository import CategoryRule, MatchType
from munger_matics.transactions.categorise import apply_rules

# ---------------------------------------------------------------------------
# Helpers — build CategoryRule objects directly without DB
# ---------------------------------------------------------------------------


def _rule(
    pattern: str,
    match_type: MatchType | str,
    category_id: str,
    priority: int = 100,
) -> CategoryRule:
    return CategoryRule(
        id="00000000-0000-0000-0000-000000000001",
        pattern=pattern,
        match_type=match_type,
        category_id=category_id,
        priority=priority,
        created_at=date(2026, 1, 1),
    )


def _df(*descriptions: str) -> pl.DataFrame:
    return pl.DataFrame({"description": list(descriptions)})


# ---------------------------------------------------------------------------
# Match types
# ---------------------------------------------------------------------------


def test_contains_match() -> None:
    rule = _rule("RATP", MatchType.CONTAINS, "cat-transport")
    result = apply_rules(_df("CARTE 01/03 RATP NAVIGO"), [rule])
    assert result["category_id"][0] == "cat-transport"


def test_contains_no_match() -> None:
    rule = _rule("SNCF", MatchType.CONTAINS, "cat-transport")
    result = apply_rules(_df("CARTE 01/03 RATP NAVIGO"), [rule])
    assert result["category_id"][0] is None


def test_starts_with_match() -> None:
    rule = _rule("VIR SALAIRE", MatchType.STARTS_WITH, "cat-salary")
    result = apply_rules(_df("VIR SALAIRE EMPLOYEUR FEVRIER"), [rule])
    assert result["category_id"][0] == "cat-salary"


def test_starts_with_no_match_mid_string() -> None:
    rule = _rule("VIR SALAIRE", MatchType.STARTS_WITH, "cat-salary")
    result = apply_rules(_df("CARTE VIR SALAIRE BLAH"), [rule])
    assert result["category_id"][0] is None


def test_regex_match() -> None:
    # Regex is case-sensitive; pattern must match the actual casing.
    rule = _rule(r"AMAZON|AMZ", MatchType.REGEX, "cat-shopping")
    result = apply_rules(_df("CARTE 09/03 AMAZON MARKETPLACE"), [rule])
    assert result["category_id"][0] == "cat-shopping"


def test_regex_no_match() -> None:
    rule = _rule(r"amazon|amz", MatchType.REGEX, "cat-shopping")
    result = apply_rules(_df("CARTE 09/03 LECLERC DRIVE"), [rule])
    assert result["category_id"][0] is None


# ---------------------------------------------------------------------------
# Case sensitivity
# ---------------------------------------------------------------------------


def test_contains_case_insensitive() -> None:
    rule = _rule("ratp", MatchType.CONTAINS, "cat-transport")
    result = apply_rules(_df("CARTE RATP NAVIGO"), [rule])
    assert result["category_id"][0] == "cat-transport"


def test_starts_with_case_insensitive() -> None:
    rule = _rule("vir salaire", MatchType.STARTS_WITH, "cat-salary")
    result = apply_rules(_df("VIR SALAIRE EMPLOYEUR"), [rule])
    assert result["category_id"][0] == "cat-salary"


def test_regex_case_sensitive_by_default() -> None:
    rule = _rule(r"amazon", MatchType.REGEX, "cat-shopping")
    result = apply_rules(_df("AMAZON MARKETPLACE"), [rule])
    # Uppercase does NOT match lowercase regex — user must use (?i) for that.
    assert result["category_id"][0] is None


def test_regex_case_insensitive_with_flag() -> None:
    rule = _rule(r"(?i)amazon", MatchType.REGEX, "cat-shopping")
    result = apply_rules(_df("AMAZON MARKETPLACE"), [rule])
    assert result["category_id"][0] == "cat-shopping"


# ---------------------------------------------------------------------------
# First-match-wins and priority ordering
# ---------------------------------------------------------------------------


def test_first_match_wins() -> None:
    # Two rules both match; lower priority number wins.
    high_priority = _rule("RATP", MatchType.CONTAINS, "cat-transport", priority=10)
    low_priority = _rule("RATP", MatchType.CONTAINS, "cat-other", priority=50)
    result = apply_rules(_df("CARTE RATP NAVIGO"), [low_priority, high_priority])
    assert result["category_id"][0] == "cat-transport"


def test_low_priority_does_not_overwrite() -> None:
    first = _rule("VIR SALAIRE", MatchType.STARTS_WITH, "cat-salary", priority=5)
    second = _rule("VIR", MatchType.STARTS_WITH, "cat-transfer", priority=20)
    result = apply_rules(_df("VIR SALAIRE EMPLOYEUR"), [second, first])
    assert result["category_id"][0] == "cat-salary"


def test_priority_ordering_applied_regardless_of_list_order() -> None:
    # Rules passed in reverse priority order — function must sort internally.
    r1 = _rule("NETFLIX", MatchType.CONTAINS, "cat-subs", priority=10)
    r2 = _rule("NETFLIX", MatchType.CONTAINS, "cat-entertainment", priority=90)
    result = apply_rules(_df("PRELEVEMENT NETFLIX"), [r2, r1])
    assert result["category_id"][0] == "cat-subs"


# ---------------------------------------------------------------------------
# Multiple rows + mixed outcomes
# ---------------------------------------------------------------------------


def test_multiple_rows_mixed_outcomes() -> None:
    rules = [
        _rule("RATP", MatchType.CONTAINS, "cat-transport", priority=10),
        _rule("VIR SALAIRE", MatchType.STARTS_WITH, "cat-salary", priority=5),
        _rule(r"amazon", MatchType.REGEX, "cat-shopping", priority=20),
    ]
    df = _df(
        "CARTE RATP NAVIGO",  # → cat-transport
        "VIR SALAIRE FEVRIER",  # → cat-salary
        "CARTE amazon marketplace",  # → cat-shopping (regex, lowercase matches)
        "PRELEVEMENT EDF",  # → None (no rule matches)
    )
    result = apply_rules(df, rules)
    cats = result["category_id"].to_list()
    assert cats[0] == "cat-transport"
    assert cats[1] == "cat-salary"
    assert cats[2] == "cat-shopping"
    assert cats[3] is None


def test_unmatched_rows_are_null() -> None:
    rule = _rule("RATP", MatchType.CONTAINS, "cat-transport")
    result = apply_rules(_df("PRELEVEMENT EDF", "CARREFOUR BIO"), [rule])
    assert result["category_id"][0] is None
    assert result["category_id"][1] is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_rules_list() -> None:
    result = apply_rules(_df("ANYTHING"), [])
    assert result["category_id"][0] is None


def test_empty_dataframe() -> None:
    rule = _rule("RATP", MatchType.CONTAINS, "cat-transport")
    empty_df = pl.DataFrame({"description": pl.Series([], dtype=pl.String)})
    result = apply_rules(empty_df, [rule])
    assert len(result) == 0


def test_existing_category_id_column_is_overwritten() -> None:
    # If df already has category_id, apply_rules resets and re-applies from scratch.
    df = pl.DataFrame(
        {
            "description": ["CARTE RATP"],
            "category_id": ["stale-cat"],
        }
    )
    rule = _rule("RATP", MatchType.CONTAINS, "cat-transport")
    result = apply_rules(df, [rule])
    assert result["category_id"][0] == "cat-transport"


def test_output_preserves_other_columns() -> None:
    df = pl.DataFrame(
        {
            "description": ["CARTE RATP"],
            "amount": [pl.Series(["-1.50"], dtype=pl.String)],
        }
    )
    rule = _rule("RATP", MatchType.CONTAINS, "cat-transport")
    result = apply_rules(df, [rule])
    assert "amount" in result.columns
    assert "category_id" in result.columns
