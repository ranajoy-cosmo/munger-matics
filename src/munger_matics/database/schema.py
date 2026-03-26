import duckdb


def initialise(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all tables if they don't exist.

    Called once at application startup. Schema is defined here
    when the data model is known.
    """
    # Tables will be added here once the schema is designed.
    pass
