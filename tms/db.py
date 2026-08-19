"""
Database access.

One connection helper, one query function. Everything that touches Postgres
goes through here, so credential resolution and parameter binding have exactly
one implementation to get right.

Resolution order for the connection string:
    1. st.secrets["DATABASE_URL"]   — Streamlit Cloud
    2. os.environ["DATABASE_URL"]   — local .env, CI
Streamlit is imported lazily so this module stays usable from plain scripts and
from pytest, where there is no Streamlit runtime.
"""

from __future__ import annotations

import os

import pandas as pd
import psycopg
from dotenv import load_dotenv

load_dotenv()

# The schema holding the analytical tables. Mirrors the mart layer in a
# warehouse: the app reads only from here and never from a raw load table.
SCHEMA = "mart"


class DatabaseNotConfigured(RuntimeError):
    """DATABASE_URL is not set anywhere we look."""


def database_url() -> str:
    """Resolve the Postgres connection string.

    Streamlit Cloud injects secrets; local runs and CI use the environment.
    """
    try:
        import streamlit as st  # noqa: PLC0415

        if "DATABASE_URL" in st.secrets:
            return str(st.secrets["DATABASE_URL"])
    except Exception:
        # No Streamlit runtime, or no secrets file. Both are normal outside
        # the deployed app, so fall through to the environment.
        pass

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise DatabaseNotConfigured(
            "DATABASE_URL is not set.\n\n"
            "  Local:           copy .env.example to .env and fill it in\n"
            "  Streamlit Cloud: add it under Settings -> Secrets\n"
            "  CI:              set it as a workflow env var\n\n"
            "Get a free Postgres database at https://neon.tech"
        )
    return url


def connect() -> psycopg.Connection:
    """Open a connection. Callers are responsible for closing it.

    Neon's free tier idles the compute after a few minutes, so the first query
    of a session can take a couple of seconds to wake it. The timeout is set
    generously enough to absorb that rather than surfacing a spurious error.
    """
    return psycopg.connect(database_url(), connect_timeout=15)


def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Execute a parameterized query and return a DataFrame.

    Parameters use pyformat placeholders — `%(name)s` — and are bound by
    psycopg, never formatted into the SQL string. A metro name with an
    apostrophe in it is therefore just a value, not a syntax error or an
    injection vector.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params or {})
        if cur.description is None:
            return pd.DataFrame()
        columns = [c.name for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=columns)


def execute(sql: str, params: dict | None = None) -> None:
    """Run a statement that returns nothing — DDL, INSERT, TRUNCATE."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params or {})


def table_exists(table: str, schema: str = SCHEMA) -> bool:
    """Whether a table is present. Used to give a useful error before the app
    tries to query a warehouse nobody has loaded yet."""
    out = run_query(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = %(schema)s AND table_name = %(table)s
        ) AS present
        """,
        {"schema": schema, "table": table},
    )
    return bool(out.iloc[0]["present"])
