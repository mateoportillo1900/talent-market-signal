"""
Print the query plan for every query in `sql/`.

Why this is in the repo
───────────────────────
"Optimize queries for performance" is easy to claim and hard to show. This
script makes the claim checkable: run it and read what the planner actually
does, rather than taking a comment's word for it.

What to look for in the output:

  Index scans, not sequential scans
      Every analytical query filters on `soc_code` first. That predicate is
      covered by `talent_market_soc_idx`, so the plan should open with a
      Bitmap Index Scan narrowing to ~40 rows, not a Seq Scan reading all
      2,520. On a table this size Postgres would be within its rights to seq
      scan anyway; the index earns its place as the row count grows.

  Sorts operating on narrowed input
      The window functions each require a sort. Those sorts should sit above
      the narrowed CTE, so they order 40 rows per occupation rather than the
      whole table.

  Nothing accidentally quadratic
      `skill_adjacency` joins every occupation's skill vector against one
      target vector. The pairwise join should be a Hash Join over ~2,200 rows.
      One Nested Loop does appear in that plan and is fine: it is the CROSS
      JOIN of the single-row target_norm CTE against the per-occupation norms,
      which is a 1 x N loop by construction.

      A seq scan on `skills` is also expected and correct — the table is 2,205
      rows and adjacency reads all of them by definition. Index scans matter
      on `talent_market`, where every query filters to one occupation.

Run `--analyze` to execute the queries and get real timings alongside the
estimates, which is the only way to catch a plan that looks fine and is not.

Usage
─────
    python scripts/explain_queries.py                    # all queries
    python scripts/explain_queries.py competition_index  # just one
    python scripts/explain_queries.py --analyze          # with real timings
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tms import db, query, schema  # noqa: E402

# Representative parameters — enough to plan each query.
SAMPLE_PARAMS: dict[str, dict[str, object]] = {
    "competition_index": {
        "soc_code": "15-1252",
        "min_employment": schema.MIN_EMPLOYMENT_FOR_INDEX,
        "w_scarcity": schema.INDEX_WEIGHTS["scarcity"],
        "w_wage_premium": schema.INDEX_WEIGHTS["wage_premium"],
        "w_growth": schema.INDEX_WEIGHTS["growth"],
    },
    "wage_arbitrage": {
        "soc_code": "15-1252",
        "baseline_area": "41860",
        "headcount": 20,
        "percentile": "p50",
        "min_employment": schema.MIN_EMPLOYMENT_FOR_INDEX,
    },
    "skill_adjacency": {"soc_code": "15-1252", "limit": 8},
    "skill_profile": {"soc_code": "15-1252"},
    "talent_pool_summary": {"soc_code": "15-1252", "area_code": "12420"},
}


def report(name: str, analyze: bool) -> None:
    params = SAMPLE_PARAMS.get(name)
    if params is None:
        print(f"  (no sample parameters registered for {name!r} — skipped)")
        return

    prefix = "EXPLAIN (ANALYZE, BUFFERS)" if analyze else "EXPLAIN"
    plan_rows = db.run_query(f"{prefix} {query.read_sql(name)}", params)
    plan = "\n".join(str(v) for v in plan_rows.iloc[:, 0])

    print("═" * 78)
    print(f"  {name}")
    print("═" * 78)
    print(plan)

    # Reported, not judged. Whether a seq scan is a problem depends entirely
    # on the query — see the module docstring for which is which.
    lowered = plan.lower()
    print()
    print(f"  index scans:   {lowered.count('index scan')}")
    print(f"  seq scans:     {lowered.count('seq scan')}")
    print(f"  hash joins:    {lowered.count('hash join')}")
    print(f"  nested loops:  {lowered.count('nested loop')}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="queries to explain (default: all)")
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="actually run the queries and report real timings",
    )
    args = parser.parse_args()

    names = args.names or [p.stem for p in query.sql_files()]
    for name in names:
        report(name, args.analyze)


if __name__ == "__main__":
    main()
