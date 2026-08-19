"""
Contract tests.

These run against whichever dataset `tms.data.load()` resolves — the fixture
in CI, the real Parquet on a developer machine. That is the point: the same
assertions hold for both, so a green CI run is meaningful evidence about the
real data too.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tms import data, schema


@pytest.fixture(scope="module")
def dataset() -> data.Dataset:
    return data.load()


# ── talent_market.parquet ────────────────────────────────────────────────────


def test_talent_has_exactly_the_contracted_columns(dataset: data.Dataset) -> None:
    assert set(dataset.talent.columns) == set(schema.TALENT_COLUMNS)


def test_talent_grain_is_unique(dataset: data.Dataset) -> None:
    dupes = dataset.talent.duplicated(subset=schema.TALENT_KEYS)
    assert not dupes.any(), (
        f"{int(dupes.sum())} duplicate (soc_code, area_code) rows — "
        "the grain is one row per occupation per metro"
    )


def test_talent_required_columns_are_never_null(dataset: data.Dataset) -> None:
    nulls = dataset.talent[schema.TALENT_NOT_NULL].isna().sum()
    offenders = nulls[nulls > 0]
    assert offenders.empty, f"nulls in non-nullable columns:\n{offenders}"


def test_wage_percentiles_are_monotonic(dataset: data.Dataset) -> None:
    """p10 <= p25 <= p50 <= p75 <= p90, row by row.

    A percentile inversion means the wage columns got crossed somewhere in the
    BLS parse. It is silent, it is plausible-looking, and it would put a wrong
    number in front of a customer.
    """
    wages = dataset.talent[schema.WAGE_PERCENTILES]
    ordered = wages.apply(
        lambda row: row.is_monotonic_increasing if row.notna().all() else True,
        axis=1,
    )
    assert ordered.all(), (
        f"{int((~ordered).sum())} rows have non-monotonic wage percentiles"
    )


def test_wages_are_positive(dataset: data.Dataset) -> None:
    wages = dataset.talent[schema.WAGE_PERCENTILES]
    assert (wages.dropna() > 0).all().all(), "found non-positive annual wages"


def test_employment_is_positive(dataset: data.Dataset) -> None:
    assert (dataset.talent["employment"] > 0).all()


def test_every_soc_code_is_in_scope(dataset: data.Dataset) -> None:
    """No occupation should reach the app that the schema does not name."""
    found = set(dataset.talent["soc_code"])
    unexpected = found - set(schema.TARGET_SOC_CODES)
    assert not unexpected, f"SOC codes outside the curated scope: {sorted(unexpected)}"


def test_occupation_labels_match_the_schema(dataset: data.Dataset) -> None:
    """Guards against a stale label surviving a rename in tms.schema."""
    labels = dataset.talent.drop_duplicates("soc_code").set_index("soc_code")
    for soc, row in labels.iterrows():
        assert row["occupation"] == schema.SOC_TO_OCCUPATION[soc]
        assert row["occupation_group"] == schema.SOC_TO_GROUP[soc]


def test_national_median_is_constant_per_occupation(dataset: data.Dataset) -> None:
    """national_wage_p50 is a national fact repeated on every metro row.

    If it varies within a SOC, the denormalization went wrong and every wage
    premium computed against it is quietly wrong too.
    """
    spread = dataset.talent.groupby("soc_code")["national_wage_p50"].nunique()
    offenders = spread[spread > 1]
    assert offenders.empty, f"national_wage_p50 varies within: {list(offenders.index)}"


# ── skills.parquet ───────────────────────────────────────────────────────────


def test_skills_has_exactly_the_contracted_columns(dataset: data.Dataset) -> None:
    assert set(dataset.skills.columns) == set(schema.SKILLS_COLUMNS)


def test_skills_grain_is_unique(dataset: data.Dataset) -> None:
    dupes = dataset.skills.duplicated(subset=schema.SKILLS_KEYS)
    assert not dupes.any(), f"{int(dupes.sum())} duplicate (soc_code, skill) rows"


def test_skill_importance_is_on_the_onet_scale(dataset: data.Dataset) -> None:
    importance = dataset.skills["importance"]
    assert importance.between(
        schema.SKILL_IMPORTANCE_MIN, schema.SKILL_IMPORTANCE_MAX
    ).all(), (
        f"importance must sit on the O*NET scale "
        f"[{schema.SKILL_IMPORTANCE_MIN}, {schema.SKILL_IMPORTANCE_MAX}]"
    )


def test_every_occupation_has_a_full_skill_vector(dataset: data.Dataset) -> None:
    """Adjacency is cosine similarity over these vectors.

    A ragged vector — one occupation missing three skills another has — makes
    similarity scores incomparable across pairs. Better to catch it here than
    to ship a confidently wrong "nearest occupations" list.
    """
    per_soc = dataset.skills.groupby("soc_code")["skill"].nunique()
    assert per_soc.nunique() == 1, (
        "occupations carry different numbers of skills: "
        f"{per_soc.min()} to {per_soc.max()}"
    )


def test_skills_cover_every_occupation_in_the_talent_frame(
    dataset: data.Dataset,
) -> None:
    missing = set(dataset.talent["soc_code"]) - set(dataset.skills["soc_code"])
    assert not missing, f"no skill vector for: {sorted(missing)}"


# ── provenance ───────────────────────────────────────────────────────────────


def test_dataset_reports_its_provenance(dataset: data.Dataset) -> None:
    assert dataset.provenance
    if dataset.is_synthetic:
        assert "SYNTHETIC" in dataset.provenance


def test_frames_are_not_empty(dataset: data.Dataset) -> None:
    assert isinstance(dataset.talent, pd.DataFrame)
    assert len(dataset.talent) > 0
    assert len(dataset.skills) > 0
