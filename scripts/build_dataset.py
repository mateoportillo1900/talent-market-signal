"""
Build the real dataset from BLS and O*NET.

Run this once. It downloads the source files, filters and reshapes them, and
writes the two Parquet files that `load_to_postgres.py` puts into the
warehouse. Raw downloads are cached in `data/raw/`, so a re-run after a
parsing fix costs nothing.

    python scripts/build_dataset.py            # full build, ~10 min first time
    python scripts/build_dataset.py --check    # verify the URLs, download nothing
    python scripts/build_dataset.py --force    # ignore the cache, re-download

What it does with awkward data
──────────────────────────────
BLS suppresses cells it cannot publish, using four different markers for four
different reasons. All become NaN. The `#` marker is the one worth knowing
about: it means "wage at or above $115,000", a censored value rather than a
missing one. Substituting $115,000 would be inventing a number, and it would
bias precisely the high-wage occupations this project is about, so it stays
null and the app shows a gap.

Metro definitions change between vintages. When a 2024 metro has no 2021
counterpart, three-year growth is null rather than guessed, and the app marks
those cells.

Design note
───────────
Every step prints what it kept and what it dropped. A quiet pipeline that
silently discards 90% of its input looks identical to one that works.
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sources  # noqa: E402
from tms import schema  # noqa: E402

# ── Download ─────────────────────────────────────────────────────────────────


def fetch(url: str, destination: Path, force: bool = False) -> Path:
    """Download a file to the raw cache, streaming so memory stays flat."""
    if destination.exists() and not force:
        size_mb = destination.stat().st_size / 1_000_000
        print(f"  cached   {destination.name}  ({size_mb:,.1f} MB)")
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"  fetching {url}")

    try:
        response = requests.get(
            url,
            headers={"User-Agent": sources.USER_AGENT},
            timeout=sources.DOWNLOAD_TIMEOUT,
            stream=True,
        )
    except requests.RequestException as exc:
        raise SystemExit(
            f"\nCould not reach {url}\n  {exc}\n\n"
            "Check your connection. If BLS is up but this still fails, the "
            "path may have moved — the URLs live in scripts/sources.py."
        ) from exc

    if response.status_code == 404:
        raise SystemExit(
            f"\n404 for {url}\n\n"
            "BLS reorganises its download paths between vintages. Open\n"
            "https://www.bls.gov/oes/tables.htm , find the current archive "
            "name,\nand update scripts/sources.py. Nothing else needs to "
            "change."
        )
    response.raise_for_status()

    # A truncated download that still unzips produces a silently short table,
    # so write to a temp path and move only once the transfer completes.
    partial = destination.with_suffix(destination.suffix + ".partial")
    written = 0
    with partial.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1 << 20):
            handle.write(chunk)
            written += len(chunk)
            print(f"\r    {written / 1_000_000:,.1f} MB", end="", flush=True)
    print()

    if written < 10_000:
        partial.unlink(missing_ok=True)
        raise SystemExit(
            f"\n{url} returned only {written} bytes — that is an error page, "
            "not a data file."
        )

    partial.replace(destination)
    return destination


def check_urls() -> int:
    """HEAD every source URL and report. Downloads nothing."""
    targets = [
        ("OES metro (current)", sources.OES_CURRENT.url),
        ("OES metro (prior)", sources.OES_PRIOR.url),
        ("OES national", sources.OES_NATIONAL.url),
        ("O*NET database", sources.ONET_URL),
        ("BLS projections (optional)", sources.EP_URL),
    ]
    failures = 0
    for label, url in targets:
        try:
            response = requests.head(
                url,
                headers={"User-Agent": sources.USER_AGENT},
                timeout=30,
                allow_redirects=True,
            )
            size = response.headers.get("content-length")
            size_note = f"  {int(size) / 1_000_000:,.0f} MB" if size else ""
            status = "OK " if response.ok else f"HTTP {response.status_code}"
            if not response.ok and "optional" not in label:
                failures += 1
            print(f"  [{status:>7}] {label:<28}{size_note}")
        except requests.RequestException as exc:
            if "optional" not in label:
                failures += 1
            print(f"  [ FAILED] {label:<28}  {exc}")
    return failures


# ── Read ─────────────────────────────────────────────────────────────────────


def read_workbook(archive: Path, member: str) -> pd.DataFrame:
    """Read one workbook out of a zip.

    Tries calamine first — it reads these 400k-row workbooks in seconds where
    openpyxl takes minutes — and falls back if it is not installed.
    """
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        match = next((n for n in names if n.endswith(member)), None)
        if match is None:
            raise SystemExit(
                f"\n{member} is not in {archive.name}.\n"
                f"The archive contains:\n  " + "\n  ".join(names[:20]) + "\n\n"
                "Update the `workbook` field in scripts/sources.py."
            )
        payload = bundle.read(match)

    for engine in ("calamine", "openpyxl"):
        try:
            return pd.read_excel(io.BytesIO(payload), engine=engine, dtype=str)
        except ImportError:
            continue
    raise SystemExit(
        "\nNo Excel engine available. Install one:\n"
        "  pip install python-calamine   (fast, recommended)\n"
        "  pip install openpyxl          (slower)"
    )


def to_number(series: pd.Series) -> pd.Series:
    """Coerce a BLS column to float, turning suppression markers into NaN.

    BLS ships numbers as strings with thousands separators and four different
    'no value here' markers. Naive `astype(float)` raises; naive `to_numeric`
    with coerce silently turns '#' into NaN too, which is right — but doing it
    explicitly documents that the nulls are censored data, not parse failures.
    """
    cleaned = (
        series.astype("string")
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
    )
    cleaned = cleaned.where(~cleaned.isin(sources.OES_SUPPRESSION))
    return pd.to_numeric(cleaned, errors="coerce")


def read_oes_metro(
    vintage: sources.OesVintage, raw_dir: Path, force: bool
) -> pd.DataFrame:
    """One OES metro vintage, filtered to in-scope occupations and metros."""
    print(f"\nOES metro {vintage.year}")
    archive = fetch(vintage.url, raw_dir / vintage.archive, force)
    frame = read_workbook(archive, vintage.workbook)
    frame.columns = [c.strip().upper() for c in frame.columns]

    cols = sources.OES_COLUMNS
    missing = [v for v in cols.values() if v not in frame.columns]
    if missing:
        raise SystemExit(
            f"\n{vintage.workbook} is missing expected columns: {missing}\n"
            f"It has: {sorted(frame.columns)[:30]}\n\n"
            "BLS renames columns occasionally. Update OES_COLUMNS in "
            "scripts/sources.py."
        )

    started = len(frame)

    # Three filters, in the order that drops the most first.
    frame = frame[frame[cols["o_group"]].str.lower() == sources.OES_DETAILED]
    frame = frame[frame[cols["occ_code"]].isin(schema.TARGET_SOC_CODES)]
    frame = frame[
        pd.to_numeric(frame[cols["area_type"]], errors="coerce")
        == sources.OES_AREA_TYPE_METRO
    ]
    if cols["naics"] in frame.columns:
        naics = frame[cols["naics"]].astype("string").str.strip()
        # Some vintages omit NAICS entirely on the metro file; only filter if
        # the cross-industry total is actually present, or we drop everything.
        if (naics == sources.OES_NAICS_ALL).any():
            frame = frame[naics == sources.OES_NAICS_ALL]

    print(f"  {started:,} rows -> {len(frame):,} after scope filters")

    out = pd.DataFrame(
        {
            "soc_code": frame[cols["occ_code"]].str.strip(),
            "area_code": frame[cols["area"]].astype("string").str.strip(),
            "metro": frame[cols["area_title"]].str.strip(),
            "state": frame[cols["state"]].astype("string").str.strip(),
            "employment": to_number(frame[cols["employment"]]),
            "employment_per_1k": to_number(frame[cols["jobs_per_1k"]]),
            "wage_p10": to_number(frame[cols["wage_p10"]]),
            "wage_p25": to_number(frame[cols["wage_p25"]]),
            "wage_p50": to_number(frame[cols["wage_p50"]]),
            "wage_p75": to_number(frame[cols["wage_p75"]]),
            "wage_p90": to_number(frame[cols["wage_p90"]]),
        }
    )

    before = len(out)
    out = out.dropna(subset=["employment", "wage_p50"])
    out = out[out["employment"] >= sources.MIN_EMPLOYMENT]
    suppressed = before - len(out)
    print(
        f"  {len(out):,} usable rows "
        f"({suppressed:,} dropped: suppressed wage or employment below "
        f"{sources.MIN_EMPLOYMENT})"
    )
    return out.drop_duplicates(subset=["soc_code", "area_code"])


def read_oes_national(raw_dir: Path, force: bool) -> pd.Series:
    """National median wage per occupation, indexed by SOC."""
    print("\nOES national")
    vintage = sources.OES_NATIONAL
    archive = fetch(vintage.url, raw_dir / vintage.archive, force)
    frame = read_workbook(archive, vintage.workbook)
    frame.columns = [c.strip().upper() for c in frame.columns]

    cols = sources.OES_COLUMNS
    frame = frame[frame[cols["o_group"]].str.lower() == sources.OES_DETAILED]
    frame = frame[frame[cols["occ_code"]].isin(schema.TARGET_SOC_CODES)]

    national = pd.Series(
        to_number(frame[cols["wage_p50"]]).to_numpy(),
        index=frame[cols["occ_code"]].str.strip().to_numpy(),
        name="national_wage_p50",
    )
    national = national[~national.index.duplicated()].dropna()
    print(f"  national median for {len(national)} occupations")
    return national


def read_onet_skills(raw_dir: Path, force: bool) -> pd.DataFrame:
    """Skill importance per BLS SOC code."""
    print("\nO*NET skills")
    archive = fetch(
        sources.ONET_URL, raw_dir / f"onet_{sources.ONET_VERSION}.zip", force
    )

    with zipfile.ZipFile(archive) as bundle:
        member = next(
            (n for n in bundle.namelist() if n.endswith(sources.ONET_SKILLS_FILE)),
            None,
        )
        if member is None:
            raise SystemExit(
                f"\n{sources.ONET_SKILLS_FILE} not found in the O*NET archive.\n"
                "Check ONET_VERSION in scripts/sources.py against "
                "https://www.onetcenter.org/database.html"
            )
        frame = pd.read_csv(bundle.open(member), sep="\t", dtype=str)

    cols = sources.ONET_COLUMNS
    frame = frame[frame[cols["scale"]] == sources.ONET_IMPORTANCE_SCALE]

    # O*NET flags ratings it considers too uncertain to use. Keeping them would
    # put noise into vectors that every similarity score is computed from.
    if cols["suppress"] in frame.columns:
        frame = frame[frame[cols["suppress"]].fillna("N").str.upper() != "Y"]

    # O*NET-SOC codes carry a detail suffix ("15-1252.00", "15-1252.01") that
    # BLS does not use. Trimming to the 7-character SOC lets them join; the
    # groupby then averages the specialisations into one profile per SOC.
    frame = frame.assign(
        soc_code=frame[cols["soc"]].str.slice(0, 7),
        importance=pd.to_numeric(frame[cols["value"]], errors="coerce"),
    )
    frame = frame[frame["soc_code"].isin(schema.TARGET_SOC_CODES)]

    out = (
        frame.groupby(["soc_code", cols["skill"]], as_index=False)["importance"]
        .mean()
        .rename(columns={cols["skill"]: "skill"})
    )
    out["importance"] = out["importance"].round(3)

    per_soc = out.groupby("soc_code")["skill"].nunique()
    print(
        f"  {len(out):,} ratings across {per_soc.size} occupations "
        f"({per_soc.min()}-{per_soc.max()} skills each)"
    )

    # Adjacency compares vectors component by component, so a ragged vector
    # makes similarity scores incomparable between pairs. Drop any occupation
    # that does not carry the full skill list rather than silently comparing
    # different-length vectors.
    full = int(per_soc.max()) if per_soc.size else 0
    ragged = per_soc[per_soc < full]
    if not ragged.empty:
        print(f"  dropping {len(ragged)} occupations with incomplete vectors")
        out = out[~out["soc_code"].isin(ragged.index)]

    return out


def read_projections(raw_dir: Path, force: bool) -> pd.Series | None:
    """Ten-year growth per occupation. Optional — returns None if unavailable."""
    print("\nBLS employment projections (optional)")
    try:
        archive = fetch(sources.EP_URL, raw_dir / "ep_occupation.xlsx", force)
    except SystemExit as exc:
        print(f"  unavailable, continuing without it\n  ({exc})")
        return None

    try:
        frame = pd.read_excel(archive, dtype=str, skiprows=1)
        frame.columns = [str(c).strip() for c in frame.columns]
        code_col = next(c for c in frame.columns if "code" in c.lower())
        growth_col = next(
            c for c in frame.columns if "percent" in c.lower() and "change" in c.lower()
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  could not parse, continuing without it ({exc})")
        return None

    series = pd.Series(
        pd.to_numeric(frame[growth_col], errors="coerce").to_numpy() / 100.0,
        index=frame[code_col].astype("string").str.strip().to_numpy(),
        name="proj_growth_10y",
    )
    series = series[~series.index.duplicated()].dropna()
    print(f"  projections for {len(series)} occupations")
    return series


# ── Assemble ─────────────────────────────────────────────────────────────────


def build_talent_frame(
    current: pd.DataFrame,
    prior: pd.DataFrame,
    national: pd.Series,
    projections: pd.Series | None,
) -> pd.DataFrame:
    """Join the pieces into the contract in tms.schema."""
    print("\nAssembling")

    # Keep the largest metros. Ranked by total employment across the in-scope
    # occupations, so the cut reflects white-collar depth rather than raw
    # metro population.
    by_metro = current.groupby("area_code")["employment"].sum()
    keep = set(by_metro.nlargest(sources.TOP_N_METROS).index)
    frame = current[current["area_code"].isin(keep)].copy()
    print(f"  {len(keep)} metros kept of {by_metro.size}")

    # Prior vintage, for three-year growth. Metro boundaries get redefined
    # between releases, so some 2024 areas have no 2021 counterpart. Those get
    # a null growth rather than a guess, and the app marks them.
    prior_lookup = prior.set_index(["soc_code", "area_code"])["employment"]
    frame["employment_prior"] = frame.set_index(["soc_code", "area_code"]).index.map(
        prior_lookup
    )

    matched = frame["employment_prior"].notna().sum()
    print(
        f"  {matched:,} of {len(frame):,} rows matched to {sources.OES_PRIOR.year} "
        f"({matched / len(frame):.0%})"
    )

    frame["supply_growth_3y"] = (
        frame["employment"] / frame["employment_prior"] - 1.0
    ).where(frame["employment_prior"] > 0)

    frame["national_wage_p50"] = frame["soc_code"].map(national)
    # float NaN, not pd.NA: the column is cast to float64 against the schema
    # contract, and NAType does not survive that cast. Projections are the
    # source most likely to be unavailable, so this path is the common one.
    frame["proj_growth_10y"] = (
        frame["soc_code"].map(projections) if projections is not None else float("nan")
    )

    frame["occupation"] = frame["soc_code"].map(schema.SOC_TO_OCCUPATION)
    frame["occupation_group"] = frame["soc_code"].map(schema.SOC_TO_GROUP)

    # The mart's CHECK constraints reject inverted percentiles at load time,
    # but failing here names the offending rows instead of surfacing a bare
    # constraint violation from Postgres.
    wages = frame[schema.WAGE_PERCENTILES]
    ordered = wages.apply(lambda row: row.dropna().is_monotonic_increasing, axis=1)
    if not ordered.all():
        bad = frame.loc[~ordered, ["soc_code", "metro", *schema.WAGE_PERCENTILES]]
        raise SystemExit(
            f"\n{len(bad)} rows have non-monotonic wage percentiles — the wage "
            f"columns are crossed somewhere in the parse.\n\n{bad.head(10)}"
        )

    out = frame[list(schema.TALENT_COLUMNS)].astype(schema.TALENT_COLUMNS)
    out = out.dropna(subset=schema.TALENT_NOT_NULL)
    print(f"  {len(out):,} facts")
    return out.sort_values(["soc_code", "area_code"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="verify the source URLs and exit"
    )
    parser.add_argument(
        "--force", action="store_true", help="re-download even if cached"
    )
    args = parser.parse_args()

    if args.check:
        print("Checking source URLs\n")
        failures = check_urls()
        print()
        if failures:
            print(f"{failures} required source(s) unreachable — see above.")
            raise SystemExit(1)
        print("All required sources reachable.")
        return

    raw_dir = schema.RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)

    current = read_oes_metro(sources.OES_CURRENT, raw_dir, args.force)
    prior = read_oes_metro(sources.OES_PRIOR, raw_dir, args.force)
    national = read_oes_national(raw_dir, args.force)
    projections = read_projections(raw_dir, args.force)
    skills = read_onet_skills(raw_dir, args.force)

    talent = build_talent_frame(current, prior, national, projections)

    # Skills must cover every occupation that survived, or the adjacency view
    # has holes. Trim the fact table to the intersection.
    covered = set(skills["soc_code"])
    before = talent["soc_code"].nunique()
    talent = talent[talent["soc_code"].isin(covered)]
    if talent["soc_code"].nunique() < before:
        dropped = before - talent["soc_code"].nunique()
        print(f"  dropped {dropped} occupations with no O*NET skill vector")

    skills = skills[skills["soc_code"].isin(set(talent["soc_code"]))]
    skills = skills.astype(schema.SKILLS_COLUMNS)

    schema.DATA_DIR.mkdir(parents=True, exist_ok=True)
    talent_path = schema.DATA_DIR / schema.TALENT_PARQUET
    skills_path = schema.DATA_DIR / schema.SKILLS_PARQUET
    talent.to_parquet(talent_path, index=False)
    skills.to_parquet(skills_path, index=False)

    print("\nWritten")
    print(
        f"  {talent_path.name:<24} {len(talent):>7,} rows  "
        f"{talent_path.stat().st_size / 1_000_000:>5.1f} MB"
    )
    print(
        f"  {skills_path.name:<24} {len(skills):>7,} rows  "
        f"{skills_path.stat().st_size / 1_000_000:>5.1f} MB"
    )
    print(
        f"\n  {talent['soc_code'].nunique()} occupations x "
        f"{talent['area_code'].nunique()} metros"
    )
    print("\nNext:  python scripts/load_to_postgres.py")


if __name__ == "__main__":
    main()
