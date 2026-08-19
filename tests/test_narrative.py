"""
Tests for the generated takeaways.

A sentence that contradicts the chart beside it is worse than no sentence: it
does not just fail to inform, it makes the reader distrust every other number
on the page. These tests exist to catch a narrative whose direction words have
drifted from the sign of the data they describe.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tms import metrics, narrative

SOC = "15-1252"
OCCUPATION = "Software Developers"


@pytest.fixture(scope="module")
def index_frame():
    return metrics.competition_index(SOC)


@pytest.fixture(scope="module")
def baseline_area() -> str:
    return str(metrics.available_metros(SOC).iloc[0]["area_code"])


# ── Formatting helpers ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, "1st"),
        (2, "2nd"),
        (3, "3rd"),
        (4, "4th"),
        (11, "11th"),
        (12, "12th"),
        (13, "13th"),
        (21, "21st"),
        (22, "22nd"),
        (101, "101st"),
    ],
)
def test_ordinals(value: int, expected: str) -> None:
    """11th, 12th, 13th are the cases a naive implementation gets wrong."""
    assert narrative._ordinal(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(500, "$500"), (12_500, "$13k"), (1_500_000, "$1.5M"), (-2_400_000, "$-2.4M")],
)
def test_money_scales(value: float, expected: str) -> None:
    assert narrative._money(value) == expected


@pytest.mark.parametrize(("value", "expected"), [(12_500, "$13k"), (13_500, "$14k")])
def test_money_rounds_half_away_from_zero(value: float, expected: str) -> None:
    """Python rounds half to even, which would render $12,500 as "$12k".

    Inconsistent-looking beside $13,500 -> $14k, and awkward to defend when
    someone checks the arithmetic in a sentence they are about to repeat.
    """
    assert narrative._money(value) == expected


# ── Competition ──────────────────────────────────────────────────────────────


def test_competition_summary_names_the_actual_extremes(index_frame) -> None:
    text = narrative.competition_summary(index_frame, OCCUPATION)
    assert index_frame.iloc[0]["metro"] in text
    assert index_frame.iloc[-1]["metro"] in text


def test_competition_summary_handles_an_empty_frame() -> None:
    empty = pd.DataFrame(
        columns=[
            "metro",
            "competition_index",
            "scarcity_score",
            "wage_premium_score",
            "growth_score",
        ]
    )
    assert "No metro" in narrative.competition_summary(empty, OCCUPATION)


# ── Pool summary ─────────────────────────────────────────────────────────────


def test_pool_summary_direction_matches_the_wage_premium(index_frame) -> None:
    """ "above" and "below" must track the sign of the premium.

    A flipped comparator here would tell a customer a market is cheap when it
    is expensive, in a sentence that reads perfectly fluently.
    """
    for area in index_frame["area_code"].head(6):
        row = metrics.talent_pool_summary(SOC, str(area))
        text = narrative.pool_summary(row)
        if row["wage_premium"] >= 0:
            assert "above the national median" in text
        else:
            assert "below the national median" in text


def test_pool_summary_growth_verb_matches_sign(index_frame) -> None:
    for area in index_frame["area_code"].head(8):
        row = metrics.talent_pool_summary(SOC, str(area))
        text = narrative.pool_summary(row)
        if bool(row["growth_unavailable"]):
            assert "unavailable" in text
        elif row["supply_growth_3y"] >= 0:
            assert "grew" in text
        else:
            assert "shrank" in text


def test_pool_summary_flags_suppressed_growth_rather_than_inventing_it() -> None:
    frame = metrics.competition_index(SOC)
    suppressed = frame[frame["growth_imputed"]]
    if suppressed.empty:
        pytest.skip("no suppressed growth cells in this dataset")
    row = metrics.talent_pool_summary(SOC, str(suppressed.iloc[0]["area_code"]))
    assert "unavailable" in narrative.pool_summary(row)


# ── Arbitrage ────────────────────────────────────────────────────────────────


def test_arbitrage_summary_reports_a_saving_when_one_exists(baseline_area) -> None:
    arb = metrics.wage_arbitrage(SOC, baseline_area, headcount=20)
    text = narrative.arbitrage_summary(arb, 20, "Baseline Metro")
    cheapest = arb.iloc[0]
    if cheapest["annual_delta_total"] < 0:
        assert cheapest["metro"] in text
        assert "saves" in text
    else:
        assert "No metro is cheaper" in text


def test_arbitrage_summary_warns_when_the_cheapest_pool_is_thin(baseline_area) -> None:
    """The guardrail, in words.

    If the cheapest metro cannot support the plan, the sentence must say so —
    otherwise the narrative recommends exactly what the chart's guardrail
    exists to prevent.
    """
    arb = metrics.wage_arbitrage(SOC, baseline_area, headcount=200)
    cheapest = arb.iloc[0]
    if cheapest["annual_delta_total"] < 0 and cheapest["pool_depth"] == "Thin":
        text = narrative.arbitrage_summary(arb, 200, "Baseline Metro")
        assert "thin" in text.lower()


def test_arbitrage_summary_handles_an_empty_frame() -> None:
    empty = pd.DataFrame(
        columns=[
            "metro",
            "annual_delta_total",
            "wage_delta_pct",
            "pool_depth",
            "area_code",
            "employment",
            "hires_supportable",
        ]
    )
    assert "No metro" in narrative.arbitrage_summary(empty, 20, "Somewhere")


# ── Skills ───────────────────────────────────────────────────────────────────


def test_skill_summary_names_the_most_distinctive_skills() -> None:
    profile = metrics.skill_profile(SOC)
    text = narrative.skill_summary(profile, OCCUPATION)
    top = profile.sort_values("distinctive", ascending=False).iloc[0]["skill"]
    assert top in text


def test_adjacency_summary_names_the_nearest_occupation() -> None:
    adjacent = metrics.skill_adjacency(SOC, limit=8)
    text = narrative.adjacency_summary(adjacent, OCCUPATION)
    assert adjacent.iloc[0]["occupation"] in text


def test_adjacency_summary_handles_an_empty_frame() -> None:
    empty = pd.DataFrame(columns=["occupation", "similarity", "shared_strengths"])
    assert "No adjacent" in narrative.adjacency_summary(empty, OCCUPATION)


# ── Usage ────────────────────────────────────────────────────────────────────


def test_usage_summary_handles_no_data() -> None:
    empty = pd.DataFrame(columns=["view_name", "events"])
    assert "No usage recorded" in narrative.usage_summary(empty, 0, 30)


def test_usage_summary_reports_the_top_view() -> None:
    by_view = pd.DataFrame(
        {"view_name": ["Talent Pool", "Cost of Talent"], "events": [70, 30]}
    )
    text = narrative.usage_summary(by_view, 100, 30)
    assert "Talent Pool" in text
    assert "70%" in text


# ── HTML rendering ───────────────────────────────────────────────────────────


def test_to_html_converts_bold() -> None:
    """The takeaway boxes are raw HTML, where Streamlit does no markdown.

    Without conversion, every metro name emitted as **Austin** reached the
    screen as literal asterisks. This was caught by driving the running app,
    not by any unit test — hence this one.
    """
    out = narrative.to_html("**Austin** is cheap")
    assert out == "<strong>Austin</strong> is cheap"


def test_to_html_converts_italics_and_code() -> None:
    assert narrative.to_html("_note_") == "<em>note</em>"
    assert narrative.to_html("*note*") == "<em>note</em>"
    assert narrative.to_html("`docs/X.md`") == "<code>docs/X.md</code>"


def test_to_html_escapes_markup_in_the_data() -> None:
    """Occupation and metro labels come from the database, not from us."""
    out = narrative.to_html("**<script>alert(1)</script>**")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert out.startswith("<strong>")


def test_to_html_leaves_plain_text_alone() -> None:
    assert narrative.to_html("no markup here") == "no markup here"


def test_every_generated_takeaway_survives_conversion(
    index_frame, baseline_area
) -> None:
    """No generated sentence should reach the screen with stray asterisks."""
    texts = [
        narrative.competition_summary(index_frame, OCCUPATION),
        narrative.pool_summary(metrics.talent_pool_summary(SOC, baseline_area)),
        narrative.arbitrage_summary(
            metrics.wage_arbitrage(SOC, baseline_area, 20), 20, "Baseline"
        ),
        narrative.skill_summary(metrics.skill_profile(SOC), OCCUPATION),
        narrative.adjacency_summary(metrics.skill_adjacency(SOC, 8), OCCUPATION),
    ]
    for text in texts:
        rendered = narrative.to_html(text)
        assert "**" not in rendered, f"unconverted bold in: {rendered[:120]}"
        assert "<strong>" in rendered or "*" not in text
