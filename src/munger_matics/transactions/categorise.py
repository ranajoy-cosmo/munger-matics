from __future__ import annotations

import polars as pl

from munger_matics.categories.repository import CategoryRule, MatchType


def apply_rules(df: pl.DataFrame, rules: list[CategoryRule]) -> pl.DataFrame:
    """Add a ``category_id`` column to a transaction DataFrame.

    Rules are applied in ascending priority order (lower number = higher
    priority).  The first rule whose pattern matches a row wins — subsequent
    rules do not overwrite it.  Rows that match no rule receive
    ``category_id = null``.

    Match semantics:
        ``contains``    — case-insensitive substring match on ``description``
        ``starts_with`` — case-insensitive prefix match on ``description``
        ``regex``       — case-sensitive regular expression match on ``description``
                          (use ``(?i)`` in the pattern for case-insensitive regex)

    Args:
        df:    DataFrame that must contain a ``description`` column (String).
               Any existing ``category_id`` column is overwritten.
        rules: List of :class:`CategoryRule` objects, typically fetched via
               ``list_rules(conn)``.

    Returns:
        A new DataFrame with an additional ``category_id`` column (String, nullable).
    """
    result = df.with_columns(pl.lit(None).cast(pl.String).alias("category_id"))

    desc = pl.col("description")

    for rule in sorted(rules, key=lambda r: r.priority):
        pattern = rule.pattern

        if rule.match_type == MatchType.CONTAINS:
            mask = desc.str.to_lowercase().str.contains(pattern.lower(), literal=True)
        elif rule.match_type == MatchType.STARTS_WITH:
            mask = desc.str.to_lowercase().str.starts_with(pattern.lower())
        else:  # MatchType.REGEX
            mask = desc.str.contains(pattern)

        if rule.amount_min is not None:
            mask = mask & (pl.col("amount") >= float(rule.amount_min))
        if rule.amount_max is not None:
            mask = mask & (pl.col("amount") <= float(rule.amount_max))

        # Only overwrite rows whose category_id is still null (first match wins).
        result = result.with_columns(
            pl.when(pl.col("category_id").is_null() & mask)
            .then(pl.lit(rule.category_id))
            .otherwise(pl.col("category_id"))
            .alias("category_id")
        )

    return result
