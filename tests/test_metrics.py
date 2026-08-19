"""
Tests for the analytical measures.

These are the tests that matter. A schema test catches a broken build; these
catch a build that succeeds and produces a confidently wrong number, which is
the failure mode that actually reaches a customer.
"""

from __future__ import annotations

import numpy as np
import pytest

from tms import data, metrics, query, schema

SOC = "15-1252"  # Software Developers — present in every metro in both datasets


@pytest.fixture(scope="module")
def metros():
    return metrics.available_metros(SOC)


@pytest.fixture(scope="module")
def baseline_area(metros) -> str:
    return str(metros.iloc[0]["area_code"])


# ── Competition Index ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def index_frame():
    return metrics.competition_index(SOC)


def test_index_weights_sum_to_one() -> None:
    """The 0-100 bound is only guaranteed while this holds."""
    assert sum(schema.INDEX_WEIGHTS.values()) == pytest.approx(1.0)


def test_index_is_bounded(index_frame) -> None:
    idx = index_frame["competition_index"]
    assert idx.between(schema.INDEX_MAX * 0, schema.INDEX_MAX).all(), (
        f"competition_index escaped [0, 100]: {idx.min()} to {idx.max()}"
    )


def test_index_components_are_bounded(index_frame) -> None:
    for col in ("scarcity_score", "wage_premium_score", "growth_score"):
        assert index_frame[col].between(0, 100).all(), f"{col} escaped [0, 100]"


def test_index_equals_its_weighted_components(index_frame) -> None:
    """The composite must be reproducible from the parts the UI displays.

    If these drift apart, the app shows a breakdown that does not add up to
    the headline score, and anyone checking the arithmetic loses trust in
    every other number on the page.
    """
    w = schema.INDEX_WEIGHTS
    recomputed = (
        w["scarcity"] * index_frame["scarcity_score"]
        + w["wage_premium"] * index_frame["wage_premium_score"]
        + w["growth"] * index_frame["growth_score"]
    )
    np.testing.assert_allclose(
        index_frame["competition_index"].to_numpy(),
        recomputed.to_numpy(),
        rtol=1e-9,
    )


def test_index_is_sorted_hardest_first(index_frame) -> None:
    assert index_frame["competition_index"].is_monotonic_decreasing
    assert index_frame["difficulty_rank"].iloc[0] == 1


def test_scarcity_is_inverse_to_supply(index_frame) -> None:
    """Thin supply must score HIGH on scarcity.

    A sign flip here is invisible — the index still returns plausible 0-100
    numbers — but it would rank the easiest metros as the hardest and send a
    customer to build a team in the worst possible city.
    """
    corr = index_frame["employment_per_1k"].corr(index_frame["scarcity_score"])
    assert corr < -0.9, f"scarcity should fall as supply rises, got r={corr:.3f}"


def test_wage_premium_score_tracks_wage_premium(index_frame) -> None:
    corr = index_frame["wage_premium"].corr(index_frame["wage_premium_score"])
    assert corr > 0.9, f"expected a strong positive relationship, got r={corr:.3f}"


def test_growth_score_is_inverse_to_growth(index_frame) -> None:
    """A shrinking pool is harder to hire from, so it must score higher."""
    frame = index_frame[~index_frame["growth_imputed"]]
    corr = frame["supply_growth_3y"].corr(frame["growth_score"])
    assert corr < -0.9, f"growth should invert into the score, got r={corr:.3f}"


def test_imputed_growth_is_flagged(index_frame) -> None:
    """Every imputed cell must be marked, so the UI can footnote it."""
    imputed = index_frame[index_frame["growth_imputed"]]
    assert imputed["supply_growth_3y"].isna().all(), (
        "a row flagged as imputed still carries a reported growth value"
    )


def test_index_rejects_an_unknown_occupation() -> None:
    with pytest.raises(ValueError, match="not an in-scope occupation"):
        metrics.competition_index("99-9999")


# ── Wage Arbitrage ───────────────────────────────────────────────────────────


def test_baseline_metro_has_zero_delta(baseline_area) -> None:
    """The metro being compared against must cost exactly nothing extra.

    A non-zero baseline means the join picked up the wrong row, and every
    saving figure on the page is measured from the wrong anchor.
    """
    out = metrics.wage_arbitrage(SOC, baseline_area, headcount=20)
    row = out[out["is_baseline"]]
    assert len(row) == 1, f"expected exactly one baseline row, got {len(row)}"
    assert row["annual_delta_total"].iloc[0] == pytest.approx(0.0)
    assert row["wage_delta_pct"].iloc[0] == pytest.approx(0.0)


def test_delta_scales_linearly_with_headcount(baseline_area) -> None:
    ten = metrics.wage_arbitrage(SOC, baseline_area, headcount=10)
    forty = metrics.wage_arbitrage(SOC, baseline_area, headcount=40)
    merged = ten.merge(forty, on="area_code", suffixes=("_10", "_40"))
    np.testing.assert_allclose(
        merged["annual_delta_total_40"].to_numpy(),
        merged["annual_delta_total_10"].to_numpy() * 4,
        rtol=1e-9,
    )


def test_delta_is_headcount_times_per_hire_difference(baseline_area) -> None:
    out = metrics.wage_arbitrage(SOC, baseline_area, headcount=17)
    np.testing.assert_allclose(
        out["annual_delta_total"].to_numpy(),
        (out["wage_at_percentile"] - out["baseline_wage"]).to_numpy() * 17,
        rtol=1e-9,
    )


def test_arbitrage_is_sorted_cheapest_first(baseline_area) -> None:
    out = metrics.wage_arbitrage(SOC, baseline_area)
    assert out["annual_delta_total"].is_monotonic_increasing


def test_percentile_choice_changes_the_answer(baseline_area) -> None:
    """p25 and p75 must not silently return the same wage.

    If the CASE in the SQL stops matching, every percentile would fall through
    to NULL or to one column, and the app's percentile selector would become a
    decorative control that changes nothing.
    """
    p25 = metrics.wage_arbitrage(SOC, baseline_area, percentile="p25")
    p75 = metrics.wage_arbitrage(SOC, baseline_area, percentile="p75")
    merged = p25.merge(p75, on="area_code", suffixes=("_25", "_75"))
    assert (merged["wage_at_percentile_75"] > merged["wage_at_percentile_25"]).all()


def test_pool_depth_labels_match_their_thresholds(baseline_area) -> None:
    out = metrics.wage_arbitrage(SOC, baseline_area, headcount=20)
    supportable = out["employment"] * metrics.ANNUAL_POOL_CAPTURE_LIMIT
    expected = np.where(
        supportable >= 60, "Deep", np.where(supportable >= 20, "Adequate", "Thin")
    )
    assert (out["pool_depth"].to_numpy() == expected).all()


def test_arbitrage_rejects_a_bad_percentile(baseline_area) -> None:
    with pytest.raises(ValueError, match="percentile must be one of"):
        metrics.wage_arbitrage(SOC, baseline_area, percentile="median")


def test_arbitrage_rejects_zero_headcount(baseline_area) -> None:
    with pytest.raises(ValueError, match="headcount must be at least 1"):
        metrics.wage_arbitrage(SOC, baseline_area, headcount=0)


# ── Skill Adjacency ──────────────────────────────────────────────────────────


def test_similarity_is_a_valid_cosine() -> None:
    out = metrics.skill_adjacency(SOC, limit=100)
    assert out["similarity"].between(-1.0, 1.0).all(), (
        "centered cosine must stay in [-1, 1]"
    )


def test_adjacency_excludes_the_query_occupation() -> None:
    out = metrics.skill_adjacency(SOC, limit=100)
    assert SOC not in set(out["soc_code"]), (
        "an occupation is trivially its own nearest neighbour; returning it "
        "wastes the top slot of a list the customer reads as recommendations"
    )


def test_adjacency_is_sorted_and_limited() -> None:
    out = metrics.skill_adjacency(SOC, limit=5)
    assert len(out) == 5
    assert out["similarity"].is_monotonic_decreasing


def test_adjacency_is_symmetric() -> None:
    """cos(a, b) == cos(b, a). Asymmetry means the normalization is wrong."""
    other = "15-2051"  # Data Scientists
    forward = metrics.skill_adjacency(SOC, limit=100)
    backward = metrics.skill_adjacency(other, limit=100)
    a = float(forward.loc[forward["soc_code"] == other, "similarity"].iloc[0])
    b = float(backward.loc[backward["soc_code"] == SOC, "similarity"].iloc[0])
    assert a == pytest.approx(b, rel=1e-9)


def test_adjacency_carries_readable_labels() -> None:
    out = metrics.skill_adjacency(SOC, limit=5)
    assert out["occupation"].notna().all()
    assert out["occupation_group"].notna().all()


def test_centering_discriminates_better_than_raw_cosine() -> None:
    """The claim in sql/skill_adjacency.sql, asserted rather than asserted-to.

    Raw cosine over strictly-positive O*NET vectors compresses every pair into
    a narrow band. If a future edit drops the mean-centering, this fails.
    """
    centered = metrics.skill_adjacency(SOC, limit=100)["similarity"]
    con = query.connect()
    raw = con.execute(
        """
        WITH target AS (SELECT skill, importance FROM skills WHERE soc_code = $soc),
        norms AS (
            SELECT soc_code, SQRT(SUM(importance * importance)) AS n
            FROM skills GROUP BY soc_code
        ),
        target_norm AS (SELECT n FROM norms WHERE soc_code = $soc),
        pairs AS (
            SELECT s.soc_code, SUM(s.importance * t.importance) AS dp
            FROM skills s JOIN target t ON s.skill = t.skill
            WHERE s.soc_code <> $soc
            GROUP BY s.soc_code
        )
        SELECT p.dp / (n.n * tn.n) AS similarity
        FROM pairs p JOIN norms n ON p.soc_code = n.soc_code CROSS JOIN target_norm tn
        """,
        {"soc": SOC},
    ).df()["similarity"]

    centered_spread = centered.max() - centered.min()
    raw_spread = raw.max() - raw.min()
    assert centered_spread > raw_spread * 3, (
        f"centering should widen the usable range substantially: "
        f"centered {centered_spread:.3f} vs raw {raw_spread:.3f}"
    )


# ── Talent Pool Summary ──────────────────────────────────────────────────────


def test_summary_returns_one_row(baseline_area) -> None:
    row = metrics.talent_pool_summary(SOC, baseline_area)
    assert row["soc_code"] == SOC
    assert row["area_code"] == baseline_area


def test_summary_shares_are_fractions(baseline_area) -> None:
    row = metrics.talent_pool_summary(SOC, baseline_area)
    assert 0.0 < row["share_of_national_pool"] <= 1.0


def test_summary_ranks_are_within_range(baseline_area) -> None:
    row = metrics.talent_pool_summary(SOC, baseline_area)
    assert 1 <= row["rank_by_size"] <= row["metros_total"]
    assert 1 <= row["rank_by_wage"] <= row["metros_total"]


def test_national_pool_shares_sum_to_one() -> None:
    """Every metro's share of the national pool, added up, must be 1.

    This is the arithmetic a customer does by eye when they see two slides in
    the same deck. If the national denominator is computed over a different
    filter than the metro rows, it will not add up and it will get noticed.
    """
    metros = metrics.available_metros(SOC)
    total = sum(
        metrics.talent_pool_summary(SOC, str(area))["share_of_national_pool"]
        for area in metros["area_code"]
    )
    assert total == pytest.approx(1.0, rel=1e-6)


def test_summary_raises_for_a_missing_combination() -> None:
    with pytest.raises(LookupError, match="No data for"):
        metrics.talent_pool_summary(SOC, "00000")


# ── Skill Profile ────────────────────────────────────────────────────────────


def test_profile_covers_the_full_skill_vector() -> None:
    out = metrics.skill_profile(SOC)
    expected = data.load().skills.query("soc_code == @SOC").shape[0]
    assert len(out) == expected


def test_profile_top_n_trims() -> None:
    assert len(metrics.skill_profile(SOC, top_n=6)) == 6


def test_distinctive_is_importance_minus_the_mean() -> None:
    out = metrics.skill_profile(SOC)
    np.testing.assert_allclose(
        out["distinctive"].to_numpy(),
        (out["importance"] - out["mean_importance"]).to_numpy(),
        rtol=1e-9,
    )


# ── Every query runs ─────────────────────────────────────────────────────────


def test_every_sql_file_is_exercised_by_a_test() -> None:
    """Guards against a query landing in sql/ with no test behind it."""
    exercised = {
        "competition_index",
        "wage_arbitrage",
        "skill_adjacency",
        "skill_profile",
        "talent_pool_summary",
    }
    on_disk = {p.stem for p in query.sql_files()}
    assert on_disk == exercised, (
        f"untested queries: {sorted(on_disk - exercised)}; "
        f"tests for missing queries: {sorted(exercised - on_disk)}"
    )
