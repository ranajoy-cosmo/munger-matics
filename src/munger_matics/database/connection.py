import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import duckdb
from dotenv import load_dotenv

load_dotenv()


def _db_path() -> Path:
    raw = os.getenv("DATABASE_PATH", "data/munger.db")
    path = Path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def get_connection() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    path = _db_path()
    conn = duckdb.connect(str(path))
    try:
        yield conn
    finally:
        conn.close()
