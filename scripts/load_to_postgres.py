"""
Load the Parquet dataset into Postgres.

This is the step between "we have files" and "we have a warehouse". It runs the
DDL in `sql/ddl/schema.sql`, then streams both tables in with COPY.

COPY rather than INSERT because it is roughly an order of magnitude faster and,
more usefully here, it is one transaction: either the whole table lands or none
of it does. A half-loaded mart that still answers queries is worse than no mart
at all, because nothing about it looks broken.

The CHECK constraints in the DDL run during the load, so a percentile inversion
or an out-of-range O*NET score fails the pipeline here rather than surfacing as
a strange-looking chart later.

Usage
─────
    python scripts/load_to_postgres.py              # real data from data/
    python scripts/load_to_postgres.py --fixture    # synthetic, for CI

Requires DATABASE_URL (see .env.example).
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tms import db, schema  # noqa: E402

DDL_PATH = schema.REPO_ROOT / "sql" / "ddl" / "schema.sql"


def resolve_source(use_fixture: bool) -> Path:
    """Where to read the Parquet from, with a useful error if it is missing."""
    source = schema.FIXTURE_DIR if use_fixture else schema.DATA_DIR
    parquet = source / schema.TALENT_PARQUET

    if not parquet.exists():
        hint = (
            "python scripts/make_fixture.py"
            if use_fixture
            else "python scripts/build_dataset.py"
        )
        raise FileNotFoundError(f"No dataset at {parquet}.\n\nBuild it with:  {hint}")
    return source


def copy_frame(conn, frame: pd.DataFrame, table: str, columns: list[str]) -> None:
    """Stream a DataFrame into a table with COPY ... FROM STDIN.

    The frame is serialized to CSV in memory. At this scale (tens of thousands
    of rows) that is far cheaper than the round trips a row-wise INSERT would
    cost, and it keeps the whole load inside one transaction.
    """
    buffer = io.StringIO()
    frame[columns].to_csv(buffer, index=False, header=False, na_rep="")
    buffer.seek(0)

    column_list = ", ".join(columns)
    statement = f"COPY {table} ({column_list}) FROM STDIN WITH (FORMAT csv, NULL '')"  # noqa: S608

    with conn.cursor() as cur, cur.copy(statement) as copy:
        copy.write(buffer.read())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="load the synthetic fixture instead of the real dataset",
    )
    args = parser.parse_args()

    source = resolve_source(args.fixture)
    label = "SYNTHETIC FIXTURE" if args.fixture else "real dataset"

    talent = pd.read_parquet(source / schema.TALENT_PARQUET)
    skills = pd.read_parquet(source / schema.SKILLS_PARQUET)

    print(f"Loading {label} from {source}")
    print(f"  talent_market  {len(talent):>7,} rows")
    print(f"  skills         {len(skills):>7,} rows")

    started = time.perf_counter()

    # One connection, one transaction. psycopg commits on a clean exit from the
    # context manager and rolls back on any exception, so a constraint
    # violation midway leaves the previous mart untouched rather than half
    # replaced.
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(DDL_PATH.read_text(encoding="utf-8"))

        copy_frame(conn, talent, "mart.talent_market", list(schema.TALENT_COLUMNS))
        copy_frame(conn, skills, "mart.skills", list(schema.SKILLS_COLUMNS))

        # Fresh statistics immediately, so the planner does not spend the first
        # few queries after a load working from an empty table's estimates.
        with conn.cursor() as cur:
            cur.execute("ANALYZE mart.talent_market")
            cur.execute("ANALYZE mart.skills")

    elapsed = time.perf_counter() - started
    print(f"\nLoaded in {elapsed:.1f}s")

    counts = db.run_query(
        """
        SELECT
            (SELECT COUNT(*) FROM mart.talent_market) AS talent_rows,
            (SELECT COUNT(*) FROM mart.skills)        AS skill_rows,
            (SELECT COUNT(DISTINCT soc_code) FROM mart.talent_market) AS occupations,
            (SELECT COUNT(DISTINCT area_code) FROM mart.talent_market) AS metros
        """
    ).iloc[0]

    print(
        f"  {counts['talent_rows']:,} facts across "
        f"{counts['occupations']} occupations x {counts['metros']} metros"
    )
    print(f"  {counts['skill_rows']:,} skill ratings")

    if args.fixture:
        print("\n  ⚠  This is synthetic data. Do not cite or screenshot it.")


if __name__ == "__main__":
    main()
