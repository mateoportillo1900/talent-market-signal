"""
The analytical measures.

Thin, typed wrappers over the queries in `sql/`. Deliberately thin: the logic
lives in SQL so it stays portable and reviewable, and these functions only bind
parameters, apply the schema's constants, and hand back a DataFrame.

If you are looking for how a number is computed, read the `.sql` file. If you
are looking for what a caller has to pass, read here.
"""

from __future__ import annotations

import pandas as pd

from tms import query, schema

# Wage percentile labels the UI may pass through to wage_arbitrage.
VALID_PERCENTILES = ("p10", "p25", "p50", "p75", "p90")

# An employer capturing more than this share of a metro's occupational pool in
# a single year is not a hiring plan, it is a fantasy. Used to judge whether a
# cheap metro is actually viable. Kept here rather than in SQL because the app
# surfaces it in the UI copy too.
ANNUAL_POOL_CAPTURE_LIMIT = 0.02


def _employment_floor(min_employment: float | None) -> float:
    """Resolve the noise floor, defaulting to the schema's value."""
    if min_employment is None:
        return schema.MIN_EMPLOYMENT_FOR_INDEX
    return min_employment


def _validate_soc(soc_code: str) -> None:
    if soc_code not in schema.SOC_TO_OCCUPATION:
        raise ValueError(
            f"{soc_code!r} is not an in-scope occupation. "
            f"See tms.schema.OCCUPATION_GROUPS ({len(schema.TARGET_SOC_CODES)} codes)."
        )


def competition_index(
    soc_code: str,
    min_employment: float | None = None,
) -> pd.DataFrame:
    """Rank every metro by how hard this occupation is to hire, 0-100.

    Returns one row per metro, sorted hardest first, with the three component
    scores exposed alongside the composite so the UI can show *why* a metro
    scored the way it did rather than asking anyone to trust a single number.
    """
    _validate_soc(soc_code)

    weights = schema.INDEX_WEIGHTS
    # A drifted weight set would silently push the index outside 0-100 and
    # every downstream comparison with it. Cheap to assert, expensive to miss.
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"INDEX_WEIGHTS must sum to 1.0, got {total}")

    return query.run(
        "competition_index",
        soc_code=soc_code,
        min_employment=_employment_floor(min_employment),
        w_scarcity=weights["scarcity"],
        w_wage_premium=weights["wage_premium"],
        w_growth=weights["growth"],
    )


def wage_arbitrage(
    soc_code: str,
    baseline_area: str,
    headcount: int = 20,
    percentile: str = "p50",
    min_employment: float | None = None,
) -> pd.DataFrame:
    """Cost of `headcount` hires in every metro, versus a baseline metro.

    Sorted cheapest first. `pool_depth` flags metros where the saving is real
    but the talent is not.
    """
    _validate_soc(soc_code)

    if percentile not in VALID_PERCENTILES:
        raise ValueError(
            f"percentile must be one of {VALID_PERCENTILES}, got {percentile!r}"
        )
    if headcount < 1:
        raise ValueError(f"headcount must be at least 1, got {headcount}")

    return query.run(
        "wage_arbitrage",
        soc_code=soc_code,
        baseline_area=baseline_area,
        headcount=headcount,
        percentile=percentile,
        min_employment=_employment_floor(min_employment),
    )


def skill_adjacency(soc_code: str, limit: int = 8) -> pd.DataFrame:
    """Occupations with the most similar skill profile, most similar first.

    Similarity is mean-centered cosine in [-1, 1]. See the header of
    `sql/skill_adjacency.sql` for why raw cosine is the wrong measure here.
    """
    _validate_soc(soc_code)
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}")

    out = query.run("skill_adjacency", soc_code=soc_code, limit=limit)
    # The SQL works in SOC codes; the UI needs names. Attaching them here keeps
    # the query portable to a warehouse where these labels live elsewhere.
    out["occupation"] = out["soc_code"].map(schema.SOC_TO_OCCUPATION)
    out["occupation_group"] = out["soc_code"].map(schema.SOC_TO_GROUP)
    return out


def skill_profile(soc_code: str, top_n: int | None = None) -> pd.DataFrame:
    """Every skill for an occupation, with raw importance and distinctiveness.

    Sorted by raw importance. Pass `top_n` to trim for a radar chart; leave it
    None to get the full vector.
    """
    _validate_soc(soc_code)
    out = query.run("skill_profile", soc_code=soc_code)
    return out.head(top_n) if top_n else out


def talent_pool_summary(soc_code: str, area_code: str) -> pd.Series:
    """Everything the Talent Pool Report needs, as a single row.

    Raises if the occupation is not reported in that metro — BLS suppresses
    small cells, and a report built on a silently-empty result would render
    with blanks where the numbers should be.
    """
    _validate_soc(soc_code)

    out = query.run("talent_pool_summary", soc_code=soc_code, area_code=area_code)
    if out.empty:
        raise LookupError(
            f"No data for {schema.SOC_TO_OCCUPATION[soc_code]} in area {area_code}. "
            "BLS suppresses estimates for small cells, so this combination may "
            "genuinely not be reported."
        )
    return out.iloc[0]


def available_metros(soc_code: str | None = None) -> pd.DataFrame:
    """Metros in the dataset, optionally only those reporting an occupation.

    Used to populate pickers, so the UI can never offer a combination that
    would come back empty.
    """
    from tms import data

    talent = data.load().talent
    if soc_code is not None:
        _validate_soc(soc_code)
        talent = talent[talent["soc_code"] == soc_code]

    return (
        talent[["area_code", "metro", "state"]]
        .drop_duplicates()
        .sort_values("metro")
        .reset_index(drop=True)
    )


# ── Warehouse scope ──────────────────────────────────────────────────────────


def mart_overview() -> pd.Series:
    """One row describing what is loaded: counts, coverage, and the wage span.

    Backs the Overview tab. Read from the warehouse rather than hardcoded in
    the UI, because the fixture and the real BLS extract differ in every one
    of these figures and a screen that states its own scope should not be able
    to be wrong about it.
    """
    return query.run("mart_overview").iloc[0]


# ── Program health ───────────────────────────────────────────────────────────


def usage_summary(days: int = 30, top_n: int = 10) -> dict:
    """Everything the Program Health view needs, in one call.

    Returns a dict rather than a frame because the view genuinely needs four
    differently-shaped results, and stitching them into one wide frame just to
    return a single object would make each harder to read.
    """
    if days < 1:
        raise ValueError(f"days must be at least 1, got {days}")

    by_day = query.run("usage_by_day", days=days)
    by_view = query.run("usage_by_view", days=days)
    top_requests = query.run("usage_top_requests", days=days, limit=top_n)

    return {
        "by_day": by_day,
        "by_view": by_view,
        "top_requests": top_requests[
            ["occupation", "occupation_group", "events", "sessions"]
        ],
        "sessions": int(by_view["sessions"].max()) if not by_view.empty else 0,
        "occupations": int(len(top_requests)),
    }
