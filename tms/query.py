"""
The SQL execution layer.

Every analytical measure in this project is computed in SQL, not in pandas.
The reason is portability: the queries in `sql/` use ANSI window functions and
CTEs, so the same logic runs on Postgres here and would run on Trino, Spark
SQL, Snowflake, or BigQuery against the same logical tables with minimal edits.
pandas logic does not travel that way.

Queries take named parameters as `%(name)s` placeholders, bound by psycopg.
Nothing is string-formatted into SQL.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import pandas as pd

from tms import db, schema

SQL_DIR = schema.REPO_ROOT / "sql"


@functools.cache
def read_sql(name: str) -> str:
    """Load a query from `sql/`, cached for the process lifetime."""
    path = SQL_DIR / f"{name}.sql"
    if not path.exists():
        available = sorted(p.stem for p in SQL_DIR.glob("*.sql"))
        raise FileNotFoundError(f"No query named {name!r}. Available: {available}")
    return path.read_text(encoding="utf-8")


def run(name: str, **params: Any) -> pd.DataFrame:
    """Execute the named query in `sql/` and return a DataFrame."""
    return db.run_query(read_sql(name), params)


def explain(name: str, **params: Any) -> str:
    """Return the planner's execution plan for a query.

    Used by `scripts/explain_queries.py` to show which access paths and joins
    Postgres actually chooses, rather than asserting performance in a comment.
    """
    plan = db.run_query(f"EXPLAIN {read_sql(name)}", params)
    return "\n".join(str(v) for v in plan.iloc[:, 0])


def sql_files() -> list[Path]:
    """Every query in `sql/`, sorted. Used by tests to smoke-run all of them."""
    return sorted(SQL_DIR.glob("*.sql"))
