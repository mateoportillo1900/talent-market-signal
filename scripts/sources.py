"""
Where the data comes from.

Every URL, filename and column name the build depends on, in one file. These
are the things most likely to break — BLS reorganises its download paths
between vintages and O*NET renames its archive every release — so isolating
them means a fix is a one-line edit here rather than a hunt through parsing
code.

If `build_dataset.py` reports a 404, this is the file to correct.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── BLS Occupational Employment and Wage Statistics ──────────────────────────
# The metro files are the spine: employment and the five wage percentiles for
# every occupation in every metropolitan area.
#
# BLS publishes each vintage as a zip containing one workbook. The path uses a
# DOT, not a hyphen — `special.requests` — which is an easy thing to mistype
# and produces a 404 that looks like the file was withdrawn.
OES_BASE = "https://www.bls.gov/oes/special.requests"


@dataclass(frozen=True)
class OesVintage:
    """One release of the OES metro file."""

    year: int
    archive: str  # filename of the zip at OES_BASE
    workbook: str  # the file to read inside it

    @property
    def url(self) -> str:
        return f"{OES_BASE}/{self.archive}"


# Current and prior vintages. Three years apart because OES re-samples on a
# rolling three-year cycle, so a shorter gap compares overlapping samples and
# understates real movement.
OES_CURRENT = OesVintage(2024, "oesm24ma.zip", "MSA_M2024_dl.xlsx")
OES_PRIOR = OesVintage(2021, "oesm21ma.zip", "MSA_M2021_dl.xlsx")

# The national file, for the per-occupation median every metro is compared
# against. Same release family as the metro files, so if one URL works the
# other almost certainly does.
OES_NATIONAL = OesVintage(2024, "oesm24nat.zip", "national_M2024_dl.xlsx")

# Columns as BLS names them in the workbook. Uppercase in recent vintages,
# lowercase in some older ones, so the reader normalises case before selecting.
OES_COLUMNS = {
    "area": "AREA",
    "area_title": "AREA_TITLE",
    "area_type": "AREA_TYPE",
    "state": "PRIM_STATE",
    "naics": "NAICS",
    "occ_code": "OCC_CODE",
    "occ_title": "OCC_TITLE",
    "o_group": "O_GROUP",
    "employment": "TOT_EMP",
    "jobs_per_1k": "JOBS_1000",
    "wage_p10": "A_PCT10",
    "wage_p25": "A_PCT25",
    "wage_p50": "A_MEDIAN",
    "wage_p75": "A_PCT75",
    "wage_p90": "A_PCT90",
}

# BLS suppression markers. Each means "no number here", for a different reason:
#   *   estimate not available
#   **  wage not released
#   #   wage at or above $115,000/yr, reported only as a threshold
#   ~   employment rounds to zero
#
# All four become NaN. The '#' case is the interesting one: it is a real
# censored value, not missing data, and treating it as $115,000 would put a
# fabricated number into a wage chart. A gap is honest; an invented ceiling is
# not, and it would bias exactly the high-wage occupations this app is about.
OES_SUPPRESSION = {"*", "**", "#", "~", "", "-"}

# AREA_TYPE 4 is a metropolitan statistical area. Other values are states,
# national, and nonmetropolitan regions, none of which belong on a metro chart.
OES_AREA_TYPE_METRO = 4

# NAICS 000000 is the cross-industry total. Without this filter every
# occupation appears once per industry and employment double-counts massively.
OES_NAICS_ALL = "000000"

# O_GROUP marks the level of the SOC hierarchy. 'detailed' is the leaf level;
# including 'major' or 'total' rows would sum children alongside their parents.
OES_DETAILED = "detailed"


# ── O*NET ────────────────────────────────────────────────────────────────────
# Skill importance ratings, which drive the skill profile and the adjacency
# measure. The version number is in the archive name and changes each release.
ONET_VERSION = "29_0"
ONET_URL = f"https://www.onetcenter.org/dl_files/database/db_{ONET_VERSION}_text.zip"
ONET_SKILLS_FILE = "Skills.txt"

# O*NET rates each skill on two scales. IM is Importance, 1-5. LV is Level,
# 0-7. Mixing them would put two different units in one vector and make every
# similarity score meaningless.
ONET_IMPORTANCE_SCALE = "IM"

ONET_COLUMNS = {
    "soc": "O*NET-SOC Code",
    "skill": "Element Name",
    "scale": "Scale ID",
    "value": "Data Value",
    "suppress": "Recommend Suppress",
}


# ── BLS Employment Projections ───────────────────────────────────────────────
# Ten-year national outlook per occupation. OPTIONAL: this table moves around
# the BLS site more than the others, and the app degrades gracefully without
# it — `proj_growth_10y` is nullable and only feeds a secondary display.
#
# If this 404s the build continues and says so, rather than failing the whole
# pipeline over a nice-to-have.
EP_URL = "https://www.bls.gov/emp/ind-occ-matrix/occupation.xlsx"
EP_COLUMNS = {
    "occ_code": "2024 National Employment Matrix code",
    "growth": "Employment change, percent, 2024–34",
}


# ── Scope ────────────────────────────────────────────────────────────────────
# Metros to keep, ranked by total employment across all occupations. The full
# set is ~400 MSAs, most of them too small to report the white-collar
# occupations this app covers. Capping keeps the committed Parquet small and
# the metro picker usable.
TOP_N_METROS = 150

# Below this, BLS estimates carry confidence intervals wide enough that the
# ranking is noise. Matches MIN_EMPLOYMENT_FOR_INDEX in tms/schema.py.
MIN_EMPLOYMENT = 50

# A polite identifier. BLS asks automated clients to identify themselves, and
# an unidentified scraper is the kind of thing that gets an IP blocked.
USER_AGENT = (
    "talent-market-signal/0.1 (portfolio project; "
    "https://github.com/mateoportillo1900/talent-market-signal)"
)

# BLS servers are slow for large files. This is generous on purpose.
DOWNLOAD_TIMEOUT = 300
