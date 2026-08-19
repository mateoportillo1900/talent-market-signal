"""
Generate a synthetic, schema-conformant dataset for tests and CI.

Why this exists
───────────────
The real dataset is a committed Parquet built from BLS and O*NET downloads.
CI has no business re-downloading 150 MB of federal flat files on every push,
and a test suite that only ever runs against one checked-in snapshot proves
less than it appears to: it cannot tell you whether the metric code is
correct or merely tuned to that snapshot.

So CI runs against this instead. The numbers are invented; the *shape* is
identical, and `tests/test_schema.py` holds both the real and the fixture
dataset to the same contract in `tms.schema`.

The output lands in `data/fixture/` (gitignored) alongside a SYNTHETIC.txt
marker. `tms.data` reads that marker and makes the app display a loud banner,
so fixture data can never quietly masquerade as real data in a screenshot.

Usage
─────
    python scripts/make_fixture.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tms import schema  # noqa: E402

SEED = 20260819

# A representative metro spread: expensive coastal hubs, mid-cost secondary
# markets, and low-cost metros, so wage-arbitrage logic gets exercised across
# a realistic range rather than a flat one.
FIXTURE_METROS: list[tuple[str, str, str, float, float]] = [
    # (area_code, metro, state, total_jobs_millions, cost_multiplier)
    ("41860", "San Francisco-Oakland-Berkeley, CA", "CA", 2.45, 1.42),
    ("41940", "San Jose-Sunnyvale-Santa Clara, CA", "CA", 1.10, 1.48),
    ("35620", "New York-Newark-Jersey City, NY-NJ", "NY", 9.60, 1.29),
    ("14460", "Boston-Cambridge-Newton, MA-NH", "MA", 2.75, 1.24),
    ("42660", "Seattle-Tacoma-Bellevue, WA", "WA", 2.05, 1.27),
    ("31080", "Los Angeles-Long Beach-Anaheim, CA", "CA", 5.90, 1.18),
    ("47900", "Washington-Arlington-Alexandria, DC-VA-MD", "DC", 2.60, 1.21),
    ("16980", "Chicago-Naperville-Elgin, IL-IN", "IL", 4.35, 1.06),
    ("12420", "Austin-Round Rock-San Marcos, TX", "TX", 1.20, 1.04),
    ("19100", "Dallas-Fort Worth-Arlington, TX", "TX", 3.85, 1.01),
    ("26420", "Houston-The Woodlands-Sugar Land, TX", "TX", 3.10, 1.00),
    ("12060", "Atlanta-Sandy Springs-Roswell, GA", "GA", 2.75, 1.00),
    ("38060", "Phoenix-Mesa-Chandler, AZ", "AZ", 2.15, 0.97),
    ("19740", "Denver-Aurora-Centennial, CO", "CO", 1.50, 1.09),
    ("33100", "Miami-Fort Lauderdale-West Palm Beach, FL", "FL", 2.70, 0.99),
    ("16740", "Charlotte-Concord-Gastonia, NC-SC", "NC", 1.25, 0.96),
    ("39580", "Raleigh-Cary, NC", "NC", 0.68, 0.98),
    ("33460", "Minneapolis-St. Paul-Bloomington, MN-WI", "MN", 1.90, 1.05),
    ("41180", "St. Louis, MO-IL", "MO", 1.30, 0.93),
    ("17140", "Cincinnati, OH-KY-IN", "OH", 1.08, 0.92),
    ("18140", "Columbus, OH", "OH", 1.05, 0.93),
    ("36420", "Oklahoma City, OK", "OK", 0.63, 0.88),
    ("28140", "Kansas City, MO-KS", "MO", 1.08, 0.94),
    ("34980", "Nashville-Davidson-Murfreesboro, TN", "TN", 1.05, 0.95),
    ("45300", "Tampa-St. Petersburg-Clearwater, FL", "FL", 1.42, 0.94),
    ("38900", "Portland-Vancouver-Hillsboro, OR-WA", "OR", 1.18, 1.08),
    ("41700", "San Antonio-New Braunfels, TX", "TX", 1.10, 0.92),
    ("29820", "Las Vegas-Henderson-North Las Vegas, NV", "NV", 1.02, 0.95),
    ("40900", "Sacramento-Roseville-Folsom, CA", "CA", 0.98, 1.12),
    ("38300", "Pittsburgh, PA", "PA", 1.12, 0.94),
    ("19820", "Detroit-Warren-Dearborn, MI", "MI", 1.85, 0.98),
    ("37980", "Philadelphia-Camden-Wilmington, PA-NJ-DE", "PA", 2.85, 1.07),
    ("12580", "Baltimore-Columbia-Towson, MD", "MD", 1.35, 1.05),
    ("41620", "Salt Lake City, UT", "UT", 0.72, 0.97),
    ("27260", "Jacksonville, FL", "FL", 0.74, 0.92),
    ("24660", "Greensboro-High Point, NC", "NC", 0.36, 0.88),
    ("13820", "Birmingham, AL", "AL", 0.52, 0.87),
    ("28940", "Knoxville, TN", "TN", 0.40, 0.86),
    ("15380", "Buffalo-Cheektowaga, NY", "NY", 0.55, 0.91),
    ("10740", "Albuquerque, NM", "NM", 0.39, 0.89),
]

# National median wage anchors by occupation group, roughly in the right order
# of magnitude so charts and dollar figures look plausible in screenshots.
GROUP_WAGE_ANCHOR: dict[str, float] = {
    "Engineering": 118_000,
    "Data & Analytics": 108_000,
    "Product & Program": 132_000,
    "Sales": 79_000,
    "Marketing & Communications": 76_000,
    "Finance & Accounting": 88_000,
    "People & HR": 82_000,
    "Operations & Supply Chain": 86_000,
    "Legal & Compliance": 112_000,
    "Healthcare Professional": 104_000,
}

# Share of a metro's total jobs that a group's occupations occupy, in
# aggregate. Drives employment counts so big metros have big pools.
GROUP_JOB_SHARE: dict[str, float] = {
    "Engineering": 0.0180,
    "Data & Analytics": 0.0060,
    "Product & Program": 0.0140,
    "Sales": 0.0230,
    "Marketing & Communications": 0.0110,
    "Finance & Accounting": 0.0190,
    "People & HR": 0.0090,
    "Operations & Supply Chain": 0.0260,
    "Legal & Compliance": 0.0075,
    "Healthcare Professional": 0.0250,
}

# O*NET-style skill vocabulary. Real O*NET has 35 skills on the Importance
# scale; this is the same list, so the adjacency math sees realistic
# dimensionality.
ONET_SKILLS: list[str] = [
    "Reading Comprehension",
    "Active Listening",
    "Writing",
    "Speaking",
    "Mathematics",
    "Science",
    "Critical Thinking",
    "Active Learning",
    "Learning Strategies",
    "Monitoring",
    "Social Perceptiveness",
    "Coordination",
    "Persuasion",
    "Negotiation",
    "Instructing",
    "Service Orientation",
    "Complex Problem Solving",
    "Operations Analysis",
    "Technology Design",
    "Equipment Selection",
    "Installation",
    "Programming",
    "Operations Monitoring",
    "Operation and Control",
    "Equipment Maintenance",
    "Troubleshooting",
    "Repairing",
    "Quality Control Analysis",
    "Judgment and Decision Making",
    "Systems Analysis",
    "Systems Evaluation",
    "Time Management",
    "Management of Financial Resources",
    "Management of Material Resources",
    "Management of Personnel Resources",
]

# Which skills each group leans on. Groups sharing a profile end up adjacent
# under cosine similarity, which is exactly the behaviour the Skills tab is
# meant to surface.
GROUP_SKILL_EMPHASIS: dict[str, list[str]] = {
    "Engineering": [
        "Programming",
        "Complex Problem Solving",
        "Systems Analysis",
        "Troubleshooting",
        "Technology Design",
        "Mathematics",
    ],
    "Data & Analytics": [
        "Mathematics",
        "Critical Thinking",
        "Systems Evaluation",
        "Programming",
        "Complex Problem Solving",
        "Operations Analysis",
    ],
    "Product & Program": [
        "Judgment and Decision Making",
        "Coordination",
        "Time Management",
        "Systems Analysis",
        "Management of Personnel Resources",
        "Speaking",
    ],
    "Sales": [
        "Persuasion",
        "Negotiation",
        "Speaking",
        "Social Perceptiveness",
        "Service Orientation",
        "Active Listening",
    ],
    "Marketing & Communications": [
        "Writing",
        "Speaking",
        "Persuasion",
        "Social Perceptiveness",
        "Active Learning",
        "Reading Comprehension",
    ],
    "Finance & Accounting": [
        "Mathematics",
        "Critical Thinking",
        "Management of Financial Resources",
        "Reading Comprehension",
        "Judgment and Decision Making",
        "Monitoring",
    ],
    "People & HR": [
        "Social Perceptiveness",
        "Active Listening",
        "Speaking",
        "Management of Personnel Resources",
        "Negotiation",
        "Service Orientation",
    ],
    "Operations & Supply Chain": [
        "Coordination",
        "Time Management",
        "Management of Material Resources",
        "Monitoring",
        "Judgment and Decision Making",
        "Operations Analysis",
    ],
    "Legal & Compliance": [
        "Reading Comprehension",
        "Critical Thinking",
        "Writing",
        "Active Listening",
        "Judgment and Decision Making",
        "Speaking",
    ],
    "Healthcare Professional": [
        "Science",
        "Active Listening",
        "Service Orientation",
        "Social Perceptiveness",
        "Critical Thinking",
        "Monitoring",
    ],
}


def build_talent_frame(rng: np.random.Generator) -> pd.DataFrame:
    """One row per (soc_code x area_code), matching TALENT_COLUMNS."""
    rows: list[dict[str, object]] = []

    # A stable per-occupation national median, so every metro row for an
    # occupation shares the same national anchor.
    national_median: dict[str, float] = {}
    for soc in schema.TARGET_SOC_CODES:
        group = schema.SOC_TO_GROUP[soc]
        anchor = GROUP_WAGE_ANCHOR[group]
        national_median[soc] = float(anchor * rng.uniform(0.80, 1.25))

    # And a stable national 10-year projection per occupation.
    proj_growth: dict[str, float] = {
        soc: float(rng.normal(0.06, 0.07)) for soc in schema.TARGET_SOC_CODES
    }

    for area_code, metro, state, total_jobs_m, cost_mult in FIXTURE_METROS:
        total_jobs = total_jobs_m * 1_000_000
        # Metro-level tech/professional tilt: some metros over-index on
        # knowledge work regardless of size.
        metro_tilt = float(rng.uniform(0.75, 1.35))

        for soc in schema.TARGET_SOC_CODES:
            group = schema.SOC_TO_GROUP[soc]
            occupations_in_group = len(schema.OCCUPATION_GROUPS[group])

            # Employment: group's share of metro jobs, split across the
            # group's occupations, jittered per occupation.
            share = GROUP_JOB_SHARE[group] / occupations_in_group
            employment = total_jobs * share * metro_tilt * rng.uniform(0.45, 1.75)
            employment = float(max(30.0, round(employment, -1)))

            # BLS suppresses small cells. Reproduce that ~4% of the time so
            # the app's null handling gets exercised.
            suppressed = employment < 120 and rng.random() < 0.45

            employment_per_1k = employment / total_jobs * 1000.0

            # Prior vintage, three years back.
            growth = float(rng.normal(0.05, 0.14))
            employment_prior = employment / (1.0 + growth)

            # Wages: national anchor x metro cost multiplier x jitter.
            median = national_median[soc] * cost_mult * rng.uniform(0.93, 1.08)
            # Percentile spread widens for higher-paying roles.
            spread = rng.uniform(0.30, 0.48)
            wage_p50 = float(round(median, -2))
            wage_p10 = float(round(wage_p50 * (1 - spread), -2))
            wage_p25 = float(round(wage_p50 * (1 - spread * 0.45), -2))
            wage_p75 = float(round(wage_p50 * (1 + spread * 0.55), -2))
            wage_p90 = float(round(wage_p50 * (1 + spread * 1.15), -2))

            rows.append(
                {
                    "soc_code": soc,
                    "occupation": schema.SOC_TO_OCCUPATION[soc],
                    "occupation_group": group,
                    "area_code": area_code,
                    "metro": metro,
                    "state": state,
                    "employment": employment,
                    "employment_per_1k": employment_per_1k,
                    "employment_prior": np.nan if suppressed else employment_prior,
                    "supply_growth_3y": np.nan if suppressed else growth,
                    "proj_growth_10y": proj_growth[soc],
                    "wage_p10": wage_p10,
                    "wage_p25": wage_p25,
                    "wage_p50": wage_p50,
                    "wage_p75": wage_p75,
                    "wage_p90": wage_p90,
                    "national_wage_p50": national_median[soc],
                }
            )

    df = pd.DataFrame(rows)
    return df.astype(schema.TALENT_COLUMNS)


def build_skills_frame(rng: np.random.Generator) -> pd.DataFrame:
    """One row per (soc_code x skill), matching SKILLS_COLUMNS."""
    rows: list[dict[str, object]] = []

    for soc in schema.TARGET_SOC_CODES:
        group = schema.SOC_TO_GROUP[soc]
        emphasized = set(GROUP_SKILL_EMPHASIS[group])
        # Per-occupation drift, so occupations within a group are similar but
        # not identical — otherwise adjacency has nothing to rank.
        drift = rng.normal(0.0, 0.35, size=len(ONET_SKILLS))

        for i, skill in enumerate(ONET_SKILLS):
            base = 3.85 if skill in emphasized else 2.15
            value = base + drift[i] + rng.normal(0.0, 0.20)
            value = float(
                np.clip(
                    value,
                    schema.SKILL_IMPORTANCE_MIN,
                    schema.SKILL_IMPORTANCE_MAX,
                )
            )
            rows.append(
                {"soc_code": soc, "skill": skill, "importance": round(value, 2)}
            )

    df = pd.DataFrame(rows)
    return df.astype(schema.SKILLS_COLUMNS)


def main() -> None:
    rng = np.random.default_rng(SEED)

    schema.FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    talent = build_talent_frame(rng)
    skills = build_skills_frame(rng)

    talent.to_parquet(schema.FIXTURE_DIR / schema.TALENT_PARQUET, index=False)
    skills.to_parquet(schema.FIXTURE_DIR / schema.SKILLS_PARQUET, index=False)

    # The marker `tms.data` looks for. Its presence is what triggers the
    # app's synthetic-data banner.
    (schema.FIXTURE_DIR / "SYNTHETIC.txt").write_text(
        "This directory contains SYNTHETIC data generated by\n"
        "scripts/make_fixture.py for tests and CI.\n\n"
        "The numbers are invented. They match the schema in tms/schema.py but\n"
        "carry no relationship to real labor market conditions. Never cite,\n"
        "screenshot, or publish anything derived from these files.\n\n"
        "Real data comes from scripts/build_dataset.py and lands in data/.\n",
        encoding="utf-8",
    )

    print(f"talent_market.parquet  {len(talent):>7,} rows")
    print(f"skills.parquet         {len(skills):>7,} rows")
    print(f"written to             {schema.FIXTURE_DIR}")


if __name__ == "__main__":
    main()
