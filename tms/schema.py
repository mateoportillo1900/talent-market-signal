"""
The column contract.

Three things read or write the Parquet files: `scripts/build_dataset.py`
(writes the real data), `scripts/make_fixture.py` (writes synthetic data for
tests), and `tms.data` (reads whichever is present). They agree here and
nowhere else, so a schema change is a one-file change.

`tests/test_schema.py` asserts both the real and the fixture datasets satisfy
these contracts, which is what makes the fixture a meaningful stand-in.
"""

from __future__ import annotations

from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
FIXTURE_DIR = DATA_DIR / "fixture"

TALENT_PARQUET = "talent_market.parquet"
SKILLS_PARQUET = "skills.parquet"

# Runtime log of every report generated — powers the Program Health tab.
REPORT_LOG = DATA_DIR / "report_log.csv"


# ── talent_market.parquet ────────────────────────────────────────────────────
# Grain: one row per (soc_code x area_code).
#
# Denormalized on purpose. `national_wage_p50` and `proj_growth_10y` are
# national-level facts repeated on every metro row. In a warehouse that would
# be a dimension join; here it keeps the app to a single pandas read with no
# join logic in the UI layer, which is the whole point of this stack.
TALENT_COLUMNS: dict[str, str] = {
    # Keys
    "soc_code": "string",  # BLS SOC, e.g. "15-1252"
    "occupation": "string",  # e.g. "Software Developers"
    "occupation_group": "string",  # our rollup, e.g. "Engineering"
    "area_code": "string",  # BLS MSA code, e.g. "12420"
    "metro": "string",  # e.g. "Austin-Round Rock-San Marcos, TX"
    "state": "string",  # primary state of the MSA
    # Supply
    "employment": "float64",  # workers employed in this occ x metro
    "employment_per_1k": "float64",  # jobs per 1,000 total metro jobs (BLS JOBS_1000)
    "employment_prior": "float64",  # same measure, prior OES vintage
    "supply_growth_3y": "float64",  # fractional change, e.g. 0.12 == +12%
    "proj_growth_10y": "float64",  # national 10-yr projection, fractional
    # Price — annual wages, USD
    "wage_p10": "float64",
    "wage_p25": "float64",
    "wage_p50": "float64",
    "wage_p75": "float64",
    "wage_p90": "float64",
    "national_wage_p50": "float64",  # national median for this SOC
}

TALENT_KEYS = ["soc_code", "area_code"]
WAGE_PERCENTILES = ["wage_p10", "wage_p25", "wage_p50", "wage_p75", "wage_p90"]

# Columns that must never be null. Everything else is nullable because BLS
# suppresses cells for confidentiality and we would rather carry an honest
# NaN than a silently imputed number.
TALENT_NOT_NULL = [
    "soc_code",
    "occupation",
    "occupation_group",
    "area_code",
    "metro",
    "state",
    "employment",
    "wage_p50",
]


# ── skills.parquet ───────────────────────────────────────────────────────────
# Grain: one row per (soc_code x skill). Long format, from the O*NET Skills
# file filtered to the Importance scale.
SKILLS_COLUMNS: dict[str, str] = {
    "soc_code": "string",
    "skill": "string",  # O*NET Element Name, e.g. "Programming"
    "importance": "float64",  # O*NET IM scale, 1.0 - 5.0
}

SKILLS_KEYS = ["soc_code", "skill"]
SKILL_IMPORTANCE_MIN = 1.0
SKILL_IMPORTANCE_MAX = 5.0


# ── Scope ────────────────────────────────────────────────────────────────────
# The occupations an LTS customer actually recruits for. BLS publishes ~830
# SOC codes; the overwhelming majority (crop workers, boilermakers, funeral
# attendants) are noise for this audience. Narrowing to ~60 white-collar
# occupations is what keeps the committed Parquet small enough to live in git.
#
# Grouped so the app can offer a two-level picker instead of a flat list of 60.
OCCUPATION_GROUPS: dict[str, dict[str, str]] = {
    "Engineering": {
        "15-1252": "Software Developers",
        "15-1253": "Software QA Analysts & Testers",
        "15-1254": "Web Developers",
        "15-1241": "Computer Network Architects",
        "15-1244": "Network & Computer Systems Administrators",
        "15-1231": "Computer Network Support Specialists",
        "15-1232": "Computer User Support Specialists",
        "15-1211": "Computer Systems Analysts",
        "15-1212": "Information Security Analysts",
        "17-2061": "Computer Hardware Engineers",
        "17-2071": "Electrical Engineers",
        "17-2112": "Industrial Engineers",
        "17-2141": "Mechanical Engineers",
    },
    "Data & Analytics": {
        "15-2051": "Data Scientists",
        "15-2041": "Statisticians",
        "15-2031": "Operations Research Analysts",
        "15-1242": "Database Administrators",
        "15-1243": "Database Architects",
        "13-2051": "Financial & Investment Analysts",
        "13-1111": "Management Analysts",
    },
    "Product & Program": {
        "11-3021": "Computer & Information Systems Managers",
        "11-9199": "Managers, All Other",
        "13-1082": "Project Management Specialists",
        "11-2021": "Marketing Managers",
        "11-3051": "Industrial Production Managers",
    },
    "Sales": {
        "41-4011": "Sales Reps, Technical & Scientific Products",
        "41-4012": "Sales Reps, Wholesale & Manufacturing",
        "41-3091": "Sales Reps of Services, All Other",
        "41-1012": "First-Line Supervisors of Non-Retail Sales Workers",
        "11-2022": "Sales Managers",
        "41-3021": "Insurance Sales Agents",
        "41-9022": "Real Estate Sales Agents",
    },
    "Marketing & Communications": {
        "13-1161": "Market Research Analysts & Marketing Specialists",
        "27-3031": "Public Relations Specialists",
        "27-1024": "Graphic Designers",
        "27-3042": "Technical Writers",
        "27-3043": "Writers & Authors",
        "27-3041": "Editors",
        "11-2032": "Public Relations Managers",
    },
    "Finance & Accounting": {
        "13-2011": "Accountants & Auditors",
        "13-2052": "Personal Financial Advisors",
        "13-2061": "Financial Examiners",
        "13-2041": "Credit Analysts",
        "11-3031": "Financial Managers",
        "13-2023": "Appraisers & Assessors of Real Estate",
        "43-3031": "Bookkeeping & Accounting Clerks",
    },
    "People & HR": {
        "13-1071": "Human Resources Specialists",
        "11-3121": "Human Resources Managers",
        "13-1141": "Compensation & Benefits Specialists",
        "13-1151": "Training & Development Specialists",
        "11-3131": "Training & Development Managers",
    },
    "Operations & Supply Chain": {
        "13-1081": "Logisticians",
        "11-3071": "Transportation, Storage & Distribution Managers",
        "13-1023": "Purchasing Agents",
        "11-1021": "General & Operations Managers",
        "43-1011": "First-Line Supervisors of Office Support Workers",
    },
    "Legal & Compliance": {
        "23-1011": "Lawyers",
        "23-2011": "Paralegals & Legal Assistants",
        "13-1041": "Compliance Officers",
    },
    "Healthcare Professional": {
        "29-1141": "Registered Nurses",
        "29-1215": "Family Medicine Physicians",
        "29-1051": "Pharmacists",
        "21-1022": "Healthcare Social Workers",
    },
}

# Flat lookups derived once at import.
SOC_TO_OCCUPATION: dict[str, str] = {
    soc: name for group in OCCUPATION_GROUPS.values() for soc, name in group.items()
}
SOC_TO_GROUP: dict[str, str] = {
    soc: group_name for group_name, group in OCCUPATION_GROUPS.items() for soc in group
}
TARGET_SOC_CODES: list[str] = sorted(SOC_TO_OCCUPATION)


# ── Competition Index weights ────────────────────────────────────────────────
# Three signals, each normalized to 0-100 across the metros in scope, then
# combined. Documented and justified in docs/METHODOLOGY.md.
#
#   scarcity      supply is thin relative to the metro's total job base
#   wage_premium  the metro pays above the national median for this role
#   growth        the local pool is shrinking, or growing slower than demand
#
# Scarcity carries the most weight because it is the signal a recruiter can
# least easily work around: you can outbid on wage, you cannot conjure people.
INDEX_WEIGHTS: dict[str, float] = {
    "scarcity": 0.50,
    "wage_premium": 0.30,
    "growth": 0.20,
}

INDEX_MIN = 0.0
INDEX_MAX = 100.0

# A metro needs at least this many workers in an occupation before we will
# score it. Below this, BLS estimates carry wide confidence intervals and the
# index becomes noise dressed up as precision.
MIN_EMPLOYMENT_FOR_INDEX = 100.0
