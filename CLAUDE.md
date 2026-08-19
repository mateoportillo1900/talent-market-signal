# Talent Market Signal — working notes for Claude Code

Labor-market insights on public U.S. data. Postgres warehouse, SQL for every
analytical measure, Streamlit for the dashboard.

## Run it

```bash
# One-time: a Postgres to point at (Neon free tier, or local)
cp .env.example .env          # then paste your DATABASE_URL

# Load data
python scripts/make_fixture.py            # synthetic, for dev and CI
python scripts/load_to_postgres.py --fixture
# ...or the real thing
python scripts/build_dataset.py           # downloads BLS + O*NET, ~10 min
python scripts/load_to_postgres.py

# Check, then run
pytest -q
ruff check . && ruff format .
streamlit run app.py
python scripts/explain_queries.py         # query plans
```

## Layout

```
app.py                  Streamlit UI. Presentation only — no analysis here.
tms/schema.py           THE CONTRACT. Column names, dtypes, occupation scope,
                        index weights. Change data shape here first.
tms/db.py               Connection + run_query. All Postgres access.
tms/query.py            Loads and executes sql/*.sql with bound parameters.
tms/metrics.py          Typed wrappers over the queries. Thin by design.
tms/data.py             Whole-table readers + usage logging.
tms/charts.py           Every Plotly figure. Validated colour palette.
sql/*.sql               The analytical logic. Read these first.
sql/ddl/schema.sql      Warehouse DDL + CHECK constraints.
scripts/                make_fixture, build_dataset, load_to_postgres, explain
tests/                  Contract tests + metric tests.
```

## Conventions that matter

**Analysis lives in SQL, not pandas.** Every measure is a file in `sql/`. This is
deliberate: the queries use ANSI window functions and CTEs so the same logic
ports to Trino, Spark SQL, Snowflake or BigQuery. pandas logic does not travel.
If you are tempted to compute something in Python, write it as SQL instead.

**Parameters bind, never interpolate.** `%(name)s` placeholders passed through
psycopg. Nothing is f-stringed into a query.

**Literal `%` in SQL must be doubled** (`%%`) or psycopg reads it as a
placeholder. This bites in comments — "30%% cheaper".

**Colours come from `tms/charts.py`, by encoding job.** Sequential blue for
magnitude, diverging blue↔red for above/below a baseline, ordinal 3-step for
Thin/Adequate/Deep. The palettes were run through a validator, not eyeballed.
Do not introduce a new colour without re-validating. Never a dual-axis chart.

**Tests target silent wrongness.** The valuable ones catch a build that succeeds
and produces a confident wrong number: a scarcity sign flip, a baseline join
picking the wrong row, a percentile selector that stops changing the answer.
When adding a measure, ask what its plausible-but-wrong failure looks like and
test for that, not just for "it returns rows".

**The fixture is not a shortcut.** CI runs against synthetic data on purpose — a
suite that only ever sees one checked-in snapshot cannot distinguish correct
code from code tuned to that snapshot. Both datasets satisfy `tms/schema.py`.

**Verify claims before writing them down.** Two comments in this repo asserted
things that turned out to be false on inspection (a cosine-similarity
illustration, a claim about a query plan). Both were caught by running the
thing. If a comment states a number or a behaviour, run it first.

## Context

Built as a portfolio project for a LinkedIn Talent Solutions insights role.
Private notes that should not ship live in `.claude/context.local.md`
(gitignored).
