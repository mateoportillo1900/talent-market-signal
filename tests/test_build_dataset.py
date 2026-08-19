"""
Tests for the BLS / O*NET parser.

The build script cannot be exercised against the real sources in CI — they are
hundreds of megabytes and behind a network. So these construct files in the
*documented shape* of the BLS workbook and the O*NET export and run the real
parsing functions over them.

That is a narrower claim than "the build works", and worth stating plainly: it
proves the parser handles the format as documented, not that BLS still ships
that format. `python scripts/build_dataset.py --check` covers the other half by
verifying the URLs resolve.

The cases here are the ones that would otherwise fail silently — suppression
markers becoming zero instead of null, industry rows double-counting
employment, SOC detail suffixes failing to join.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from scripts import build_dataset, sources
from tms import schema

SOC = "15-1252"
OTHER_SOC = "15-2051"


# ── to_number ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("marker", ["*", "**", "#", "~", "", "-"])
def test_suppression_markers_become_null_not_zero(marker: str) -> None:
    """Every BLS 'no value' marker must become NaN.

    Zero is the dangerous failure: a suppressed wage read as $0 drags every
    average down and shows up as a suspiciously cheap metro rather than as an
    obvious error.
    """
    out = build_dataset.to_number(pd.Series([marker, "123"]))
    assert pd.isna(out.iloc[0]), f"{marker!r} did not become NaN"
    assert out.iloc[1] == 123


def test_to_number_strips_formatting() -> None:
    out = build_dataset.to_number(pd.Series(["1,234", "$5,678", " 90 "]))
    assert list(out) == [1234.0, 5678.0, 90.0]


def test_hash_marker_is_null_not_the_threshold() -> None:
    """'#' means 'at or above $115,000', a censored value.

    Substituting 115000 would invent a number, and would bias exactly the
    high-wage occupations this project is about.
    """
    out = build_dataset.to_number(pd.Series(["#"]))
    assert pd.isna(out.iloc[0])


# ── A synthetic BLS workbook ─────────────────────────────────────────────────


def _oes_row(**overrides) -> dict:
    row = {
        "AREA": "12420",
        "AREA_TITLE": "Austin-Round Rock, TX",
        "AREA_TYPE": "4",
        "PRIM_STATE": "TX",
        "NAICS": "000000",
        "OCC_CODE": SOC,
        "OCC_TITLE": "Software Developers",
        "O_GROUP": "detailed",
        "TOT_EMP": "5,000",
        "JOBS_1000": "8.5",
        "A_PCT10": "70,000",
        "A_PCT25": "90,000",
        "A_MEDIAN": "120,000",
        "A_PCT75": "150,000",
        "A_PCT90": "185,000",
    }
    row.update(overrides)
    return row


def _write_archive(rows: list[dict], tmp_path: Path, workbook: str) -> Path:
    """Package rows as a BLS-shaped xlsx inside a zip."""
    buffer = io.BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False, engine="openpyxl")
    archive = tmp_path / "oes.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(workbook, buffer.getvalue())
    return archive


@pytest.fixture
def vintage() -> sources.OesVintage:
    return sources.OesVintage(2024, "oes.zip", "MSA_test.xlsx")


def _read(rows: list[dict], tmp_path: Path, vintage, monkeypatch) -> pd.DataFrame:
    archive = _write_archive(rows, tmp_path, vintage.workbook)
    monkeypatch.setattr(build_dataset, "fetch", lambda *a, **k: archive)
    return build_dataset.read_oes_metro(vintage, tmp_path, force=False)


def test_parses_a_well_formed_row(tmp_path, vintage, monkeypatch) -> None:
    out = _read([_oes_row()], tmp_path, vintage, monkeypatch)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["soc_code"] == SOC
    assert row["area_code"] == "12420"
    assert row["employment"] == 5000
    assert row["wage_p50"] == 120_000
    assert row["wage_p90"] == 185_000


def test_drops_non_metro_areas(tmp_path, vintage, monkeypatch) -> None:
    """AREA_TYPE 4 is a metro. States and national totals must not slip in.

    A state row carries the same columns and looks perfectly valid; left in,
    "Texas" would appear in the metro picker alongside Austin.
    """
    rows = [_oes_row(), _oes_row(AREA="48", AREA_TITLE="Texas", AREA_TYPE="2")]
    out = _read(rows, tmp_path, vintage, monkeypatch)
    assert list(out["area_code"]) == ["12420"]


def test_drops_industry_rows_that_would_double_count(
    tmp_path, vintage, monkeypatch
) -> None:
    """Only the cross-industry total (NAICS 000000).

    Without this, an occupation appears once per industry and summing
    employment across a metro overstates the pool several times over.
    """
    rows = [_oes_row(), _oes_row(NAICS="541500", TOT_EMP="2,000")]
    out = _read(rows, tmp_path, vintage, monkeypatch)
    assert len(out) == 1
    assert out.iloc[0]["employment"] == 5000


def test_drops_summary_soc_levels(tmp_path, vintage, monkeypatch) -> None:
    """'major' rows are parents of the detailed rows and would be counted twice."""
    rows = [_oes_row(), _oes_row(O_GROUP="major", OCC_CODE=SOC, TOT_EMP="99,000")]
    out = _read(rows, tmp_path, vintage, monkeypatch)
    assert len(out) == 1
    assert out.iloc[0]["employment"] == 5000


def test_drops_occupations_outside_scope(tmp_path, vintage, monkeypatch) -> None:
    rows = [_oes_row(), _oes_row(OCC_CODE="45-2041", OCC_TITLE="Graders, Agricultural")]
    out = _read(rows, tmp_path, vintage, monkeypatch)
    assert set(out["soc_code"]) == {SOC}


def test_drops_rows_with_a_suppressed_median_wage(
    tmp_path, vintage, monkeypatch
) -> None:
    """A row with no median is not usable — the whole app compares medians."""
    rows = [_oes_row(), _oes_row(AREA="99999", AREA_TITLE="Nowhere, XX", A_MEDIAN="*")]
    out = _read(rows, tmp_path, vintage, monkeypatch)
    assert list(out["area_code"]) == ["12420"]


def test_drops_rows_below_the_noise_floor(tmp_path, vintage, monkeypatch) -> None:
    rows = [_oes_row(), _oes_row(AREA="99999", AREA_TITLE="Tiny, XX", TOT_EMP="10")]
    out = _read(rows, tmp_path, vintage, monkeypatch)
    assert list(out["area_code"]) == ["12420"]


def test_keeps_a_row_whose_top_wage_is_censored(tmp_path, vintage, monkeypatch) -> None:
    """A '#' in p90 must not discard an otherwise good row.

    High-wage occupations are exactly where '#' appears, so dropping those
    rows would quietly remove the most interesting metros from the analysis.
    """
    out = _read([_oes_row(A_PCT90="#")], tmp_path, vintage, monkeypatch)
    assert len(out) == 1
    assert pd.isna(out.iloc[0]["wage_p90"])
    assert out.iloc[0]["wage_p50"] == 120_000


def test_missing_columns_fail_loudly(tmp_path, vintage, monkeypatch) -> None:
    """A renamed BLS column must stop the build, not produce a short table."""
    row = _oes_row()
    del row["A_MEDIAN"]
    with pytest.raises(SystemExit, match="missing expected columns"):
        _read([row], tmp_path, vintage, monkeypatch)


def test_lowercase_headers_are_handled(tmp_path, vintage, monkeypatch) -> None:
    """Older vintages ship lowercase headers."""
    row = {k.lower(): v for k, v in _oes_row().items()}
    out = _read([row], tmp_path, vintage, monkeypatch)
    assert len(out) == 1


def test_a_missing_workbook_names_what_the_archive_holds(tmp_path, monkeypatch) -> None:
    archive = _write_archive([_oes_row()], tmp_path, "SOMETHING_ELSE.xlsx")
    monkeypatch.setattr(build_dataset, "fetch", lambda *a, **k: archive)
    bad = sources.OesVintage(2024, "oes.zip", "MSA_expected.xlsx")
    with pytest.raises(SystemExit, match="is not in"):
        build_dataset.read_oes_metro(bad, tmp_path, force=False)


# ── O*NET ────────────────────────────────────────────────────────────────────


def _onet_rows() -> pd.DataFrame:
    cols = sources.ONET_COLUMNS
    rows = []
    for soc_suffix in (".00", ".01"):
        for skill, value in [("Programming", "4.0"), ("Negotiation", "2.0")]:
            rows.append(
                {
                    cols["soc"]: f"{SOC}{soc_suffix}",
                    cols["skill"]: skill,
                    cols["scale"]: "IM",
                    cols["value"]: value,
                    cols["suppress"]: "N",
                }
            )
    # A Level-scale row on a different unit, and a suppressed rating.
    rows.append(
        {
            cols["soc"]: f"{SOC}.00",
            cols["skill"]: "Programming",
            cols["scale"]: "LV",
            cols["value"]: "6.0",
            cols["suppress"]: "N",
        }
    )
    rows.append(
        {
            cols["soc"]: f"{OTHER_SOC}.00",
            cols["skill"]: "Programming",
            cols["scale"]: "IM",
            cols["value"]: "3.0",
            cols["suppress"]: "Y",
        }
    )
    return pd.DataFrame(rows)


def _write_onet(tmp_path: Path) -> Path:
    archive = tmp_path / "onet.zip"
    payload = _onet_rows().to_csv(sep="\t", index=False)
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(f"db_29_0_text/{sources.ONET_SKILLS_FILE}", payload)
    return archive


def test_onet_averages_soc_specialisations(tmp_path, monkeypatch) -> None:
    """ "15-1252.00" and "15-1252.01" are one BLS occupation.

    Without trimming the suffix, nothing joins to BLS at all and the skills
    table comes out empty — a failure that looks like missing data rather
    than a key mismatch.
    """
    monkeypatch.setattr(build_dataset, "fetch", lambda *a, **k: _write_onet(tmp_path))
    out = build_dataset.read_onet_skills(tmp_path, force=False)
    assert set(out["soc_code"]) == {SOC}
    programming = out[out["skill"] == "Programming"]["importance"].iloc[0]
    assert programming == pytest.approx(4.0)


def test_onet_keeps_only_the_importance_scale(tmp_path, monkeypatch) -> None:
    """IM is 1-5, LV is 0-7. Mixing them breaks every similarity score."""
    monkeypatch.setattr(build_dataset, "fetch", lambda *a, **k: _write_onet(tmp_path))
    out = build_dataset.read_onet_skills(tmp_path, force=False)
    assert (
        out["importance"]
        .between(schema.SKILL_IMPORTANCE_MIN, schema.SKILL_IMPORTANCE_MAX)
        .all()
    )


def test_onet_drops_suppressed_ratings(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(build_dataset, "fetch", lambda *a, **k: _write_onet(tmp_path))
    out = build_dataset.read_onet_skills(tmp_path, force=False)
    assert OTHER_SOC not in set(out["soc_code"])


def test_onet_output_matches_the_schema_contract(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(build_dataset, "fetch", lambda *a, **k: _write_onet(tmp_path))
    out = build_dataset.read_onet_skills(tmp_path, force=False)
    assert set(out.columns) == set(schema.SKILLS_COLUMNS)


# ── Assembly ─────────────────────────────────────────────────────────────────


def _talent_row(**overrides) -> dict:
    row = {
        "soc_code": SOC,
        "area_code": "12420",
        "metro": "Austin, TX",
        "state": "TX",
        "employment": 5000.0,
        "employment_per_1k": 8.5,
        "wage_p10": 70_000.0,
        "wage_p25": 90_000.0,
        "wage_p50": 120_000.0,
        "wage_p75": 150_000.0,
        "wage_p90": 185_000.0,
    }
    row.update(overrides)
    return row


def test_assembly_computes_growth_and_flags_unmatched_metros() -> None:
    current = pd.DataFrame(
        [
            _talent_row(),
            _talent_row(area_code="99999", metro="New Metro, XX", employment=1000.0),
        ]
    )
    prior = pd.DataFrame([_talent_row(employment=4000.0)])
    national = pd.Series({SOC: 110_000.0})

    out = build_dataset.build_talent_frame(current, prior, national, None)

    austin = out[out["area_code"] == "12420"].iloc[0]
    assert austin["supply_growth_3y"] == pytest.approx(0.25)

    # A metro with no prior counterpart gets a null, not a guess.
    new_metro = out[out["area_code"] == "99999"].iloc[0]
    assert pd.isna(new_metro["supply_growth_3y"])


def test_assembly_rejects_crossed_wage_columns() -> None:
    """The failure this guards against is silent and plausible-looking.

    If two wage columns get swapped in the parse, every number still looks
    like a wage. Failing here names the rows; letting it through means a
    customer sees a p25 above a p75.
    """
    current = pd.DataFrame([_talent_row(wage_p25=200_000.0)])
    prior = pd.DataFrame([_talent_row()])
    national = pd.Series({SOC: 110_000.0})

    with pytest.raises(SystemExit, match="non-monotonic wage percentiles"):
        build_dataset.build_talent_frame(current, prior, national, None)


def test_assembly_output_satisfies_the_schema_contract() -> None:
    current = pd.DataFrame([_talent_row()])
    prior = pd.DataFrame([_talent_row(employment=4500.0)])
    national = pd.Series({SOC: 110_000.0})
    projections = pd.Series({SOC: 0.17})

    out = build_dataset.build_talent_frame(current, prior, national, projections)

    assert list(out.columns) == list(schema.TALENT_COLUMNS)
    assert out[schema.TALENT_NOT_NULL].notna().all().all()
    assert out.iloc[0]["occupation"] == schema.SOC_TO_OCCUPATION[SOC]
    assert out.iloc[0]["occupation_group"] == schema.SOC_TO_GROUP[SOC]
    assert out.iloc[0]["proj_growth_10y"] == pytest.approx(0.17)


def test_assembly_survives_missing_projections() -> None:
    """The projections file is optional and the most likely to 404.

    Filling the column with pandas' NA rather than a float NaN breaks the cast
    to the schema's float64 contract — so the common path (projections
    unavailable) was the one that failed.
    """
    current = pd.DataFrame([_talent_row()])
    prior = pd.DataFrame([_talent_row(employment=4500.0)])
    national = pd.Series({SOC: 110_000.0})

    out = build_dataset.build_talent_frame(current, prior, national, None)

    assert len(out) == 1
    assert pd.isna(out.iloc[0]["proj_growth_10y"])
    assert out["proj_growth_10y"].dtype == "float64"
