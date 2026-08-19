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

import contextlib
import os
import threading
from collections.abc import Iterator

import pandas as pd
import psycopg
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

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


# Pool sizing. Neon's free tier caps concurrent connections, and Streamlit
# re-runs the whole script on every widget interaction — so a small reused pool
# matters far more here than it would against a local database.
POOL_MIN = 0  # no eager connect, so importing this module never needs a network
POOL_MAX = 3
POOL_TIMEOUT = 20.0

# Serverless Postgres suspends compute when idle, which silently kills pooled
# connections. Without a liveness check the first query after a quiet spell
# fails with a closed-connection error that looks like a bug in the app.
CONNECT_TIMEOUT = 15

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def pool() -> ConnectionPool:
    """The shared connection pool, created on first use.

    Opening a fresh connection per query is fine against a local socket and
    expensive against a hosted database — every query would pay a full TLS
    handshake over the internet, and a free tier's connection cap is reachable
    faster than it looks.
    """
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ConnectionPool(
                    conninfo=database_url(),
                    min_size=POOL_MIN,
                    max_size=POOL_MAX,
                    timeout=POOL_TIMEOUT,
                    kwargs={"connect_timeout": CONNECT_TIMEOUT},
                    # Validate before handing a connection out. A serverless
                    # database that idled will have dropped it; this discards
                    # the dead one and opens a fresh one instead of failing
                    # the query the user is waiting on.
                    check=ConnectionPool.check_connection,
                    # Explicit: psycopg_pool is changing this default, and an
                    # unpinned default that flips under you is a silent
                    # behaviour change on a routine dependency bump.
                    open=True,
                )
    return _pool


def reset_pool() -> None:
    """Close and forget the pool. For tests that swap DATABASE_URL."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


@contextlib.contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Borrow a pooled connection for the duration of the block.

    The connection is returned to the pool on exit, and psycopg commits on a
    clean exit or rolls back on an exception — so a caller wrapping several
    statements in one `with` gets a single atomic transaction. That is what
    `load_to_postgres.py` relies on.
    """
    with pool().connection() as conn:
        yield conn


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
