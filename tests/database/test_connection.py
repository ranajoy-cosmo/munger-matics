import pytest
import duckdb
from munger_matics.database.connection import get_connection
from munger_matics.database.schema import initialise


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    with get_connection() as conn:
        yield conn


def test_connection_opens(db):
    assert isinstance(db, duckdb.DuckDBPyConnection)


def test_connection_is_queryable(db):
    result = db.execute("SELECT 42 AS answer").fetchone()
    assert result == (42,)


def test_initialise_runs_without_error(db):
    initialise(db)
