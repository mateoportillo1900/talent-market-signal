"""
Read the mart.

Thin readers over the two warehouse tables, for the cases that genuinely need
a whole table in memory — populating a picker, running a contract test. The
analytical work does not come through here; it goes through `tms.query` so the
computation happens in the database.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

import pandas as pd

from tms import db


class MartNotLoaded(RuntimeError):
    """The schema exists but the tables are missing or empty."""


@dataclass(frozen=True)
class Dataset:
    """Both mart tables, plus provenance."""

    talent: pd.DataFrame
    skills: pd.DataFrame
    is_synthetic: bool

    @property
    def provenance(self) -> str:
        if self.is_synthetic:
            return "SYNTHETIC FIXTURE — invented numbers, for testing only"
        return (
            "BLS OES (May 2024 + May 2021) · O*NET 29.0 · "
            "BLS Employment Projections 2024-34"
        )


def is_synthetic() -> bool:
    """Whether the loaded mart came from the fixture rather than real data.

    Detected structurally rather than from a flag column: the fixture's metro
    set is a fixed list of 40, while the real build carries every MSA BLS
    reports. Any dataset that small is the fixture.

    The app uses this to display a banner, so a screenshot of synthetic data
    can never be mistaken for the real thing.
    """
    out = db.run_query(
        "SELECT COUNT(DISTINCT area_code) AS metros FROM mart.talent_market"
    )
    return int(out.iloc[0]["metros"]) <= 45


def require_mart() -> None:
    """Fail early and helpfully if nobody has loaded the warehouse."""
    for table in ("talent_market", "skills"):
        if not db.table_exists(table):
            raise MartNotLoaded(
                f"mart.{table} does not exist.\n\n"
                "Load it with:\n"
                "  python scripts/make_fixture.py\n"
                "  python scripts/load_to_postgres.py --fixture\n\n"
                "Or, for real data:\n"
                "  python scripts/build_dataset.py\n"
                "  python scripts/load_to_postgres.py"
            )

    counts = db.run_query("SELECT COUNT(*) AS n FROM mart.talent_market")
    if int(counts.iloc[0]["n"]) == 0:
        raise MartNotLoaded("mart.talent_market exists but is empty.")


def load() -> Dataset:
    """Read both mart tables in full. Used by contract tests and pickers."""
    require_mart()
    return Dataset(
        talent=db.run_query("SELECT * FROM mart.talent_market"),
        skills=db.run_query("SELECT * FROM mart.skills"),
        is_synthetic=is_synthetic(),
    )


def log_usage(
    view_name: str,
    soc_code: str | None = None,
    area_code: str | None = None,
    session_id: str | None = None,
) -> None:
    """Record that someone looked at something.

    Fire-and-forget: a failed write must never break the view a user is
    looking at. Instrumentation that can take the app down is worse than no
    instrumentation.
    """
    with contextlib.suppress(Exception):
        db.execute(
            """
            INSERT INTO mart.usage_log (view_name, soc_code, area_code, session_id)
            VALUES (%(view_name)s, %(soc_code)s, %(area_code)s, %(session_id)s)
            """,
            {
                "view_name": view_name,
                "soc_code": soc_code,
                "area_code": area_code,
                "session_id": session_id,
            },
        )
