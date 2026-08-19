"""
Print the physical plan for every query in `sql/`.

Why this is in the repo
───────────────────────
"Optimize queries for performance" is easy to claim and hard to show. This
script makes the claim checkable: run it and read what the engine actually
does, rather than taking a comment's word for it.

The two things worth looking for in the output:

  Filters pushed into the Parquet scan
      The `soc_code = ...` predicate should appear on the PARQUET_SCAN node,
      not as a separate FILTER above it. Pushed down, DuckDB skips row groups
      whose statistics rule them out and never decompresses them. Left above,
      it reads the whole file and discards most of it.

  Projection pushdown
      The scan node should list only the columns the query names. Reading 6 of
      17 columns off a columnar file is 6/17 of the I/O.

Both behaviours carry to Trino and Spark SQL over Parquet, which is the point
of writing the queries in portable SQL rather than in pandas.

Usage
─────
    python scripts/explain_queries.py            # all queries
    python scripts/explain_queries.py competition_index
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tms import query, schema  # noqa: E402

# Representative parameters — enough to plan each query. The values do not
# affect the shape of the plan, only which row groups survive the scan.
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


def report(name: str) -> None:
    params = SAMPLE_PARAMS.get(name)
    if params is None:
        print(f"  (no sample parameters registered for {name!r} — skipped)")
        return

    plan = query.explain(name, **params)

    print("═" * 78)
    print(f"  {name}")
    print("═" * 78)
    print(plan)
    print()

    # A crude but honest check: did the predicate reach the scan node?
    scan_lines = [ln for ln in plan.splitlines() if "PARQUET_SCAN" in ln.upper()]
    pushed = "soc_code" in plan and any("Filters" in ln for ln in plan.splitlines())
    print(f"  parquet scan nodes:  {len(scan_lines)}")
    print(f"  filter pushdown:     {'yes' if pushed else 'not detected'}")
    print()


def main() -> None:
    names = sys.argv[1:] or [p.stem for p in query.sql_files()]
    for name in names:
        report(name)


if __name__ == "__main__":
    main()
