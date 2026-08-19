"""
The SQL execution layer.

Every analytical measure in this project is computed in SQL, not in pandas.
That is a deliberate choice, and the reason is portability: the queries in
`sql/` are written in ANSI-standard SQL that runs on DuckDB here and would run
on Trino or Spark SQL against the same logical tables with near-zero edits.
Window functions, CTEs, and `QUALIFY` all carry over. pandas does not.

DuckDB reads the Parquet files directly off disk — there is no server, no load
step, and no copy of the data in a second format. `data/*.parquet` is the
warehouse.

Parameter binding
─────────────────
Queries take named parameters via `$name` placeholders and DuckDB's `params=`
argument. Nothing is string-formatted into SQL, so a metro name containing an
apostrophe cannot break a query or inject anything.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from tms import data, schema

SQL_DIR = schema.REPO_ROOT / "sql"


@functools.cache
def read_sql(name: str) -> str:
    """Load a query from `sql/`, cached for the process lifetime."""
    path = SQL_DIR / f"{name}.sql"
    if not path.exists():
        available = sorted(p.stem for p in SQL_DIR.glob("*.sql"))
        raise FileNotFoundError(f"No query named {name!r}. Available: {available}")
    return path.read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def connect() -> duckdb.DuckDBPyConnection:
    """An in-process DuckDB connection with the Parquet files registered as views.

    Registering views (rather than importing the data into DuckDB tables) means
    the Parquet files stay the single source of truth. Re-running
    `build_dataset.py` is picked up on the next process start with no reload.

    Cached because Streamlit reruns the script top-to-bottom on every widget
    interaction, and reopening the connection each time would re-plan every
    query for nothing.
    """
    source_dir, _ = data.resolve_source()
    con = duckdb.connect(database=":memory:")

    # DuckDB resolves these lazily and pushes projections and filters down into
    # the Parquet reader, so a query touching three columns of one occupation
    # never materializes the whole file.
    #
    # DDL cannot take bound parameters in DuckDB, so the path is inlined. It
    # comes from `resolve_source()` — a repo-relative directory, never user
    # input — and the quote-doubling still holds for a checkout living under a
    # path with an apostrophe in it.
    for view, filename in (
        ("talent", schema.TALENT_PARQUET),
        ("skills", schema.SKILLS_PARQUET),
    ):
        literal = str(source_dir / filename).replace("'", "''")
        con.execute(f"CREATE VIEW {view} AS SELECT * FROM read_parquet('{literal}')")

    return con


def run(name: str, **params: Any) -> pd.DataFrame:
    """Execute the named query in `sql/` and return a DataFrame.

    Keyword arguments bind to `$name` placeholders in the SQL.
    """
    sql = read_sql(name)
    con = connect()
    return con.execute(sql, params).df()


def explain(name: str, **params: Any) -> str:
    """Return DuckDB's physical plan for a query.

    Used by `scripts/explain_queries.py` and quoted in docs/METHODOLOGY.md to
    show which filters get pushed down into the Parquet scan rather than
    applied after a full read.
    """
    sql = read_sql(name)
    con = connect()
    rows = con.execute(f"EXPLAIN {sql}", params).fetchall()
    return "\n".join(str(row[1]) for row in rows)


def reset() -> None:
    """Drop the cached connection. Tests call this after swapping datasets."""
    connect.cache_clear()
    read_sql.cache_clear()


def sql_files() -> list[Path]:
    """Every query in `sql/`, sorted. Used by tests to smoke-run all of them."""
    return sorted(SQL_DIR.glob("*.sql"))
