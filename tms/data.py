"""
Load the dataset.

Resolution order is deliberate: real data if it is present, synthetic fixture
otherwise, and a clear error if neither is. Nothing here silently invents
data — if the app is running on the fixture, `load()` says so and the UI is
expected to shout about it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from tms import schema


class DatasetNotFound(FileNotFoundError):
    """Neither the real Parquet nor the fixture is on disk."""


@dataclass(frozen=True)
class Dataset:
    """Everything the app reads, plus provenance."""

    talent: pd.DataFrame
    skills: pd.DataFrame
    source_dir: Path
    is_synthetic: bool

    @property
    def provenance(self) -> str:
        if self.is_synthetic:
            return "SYNTHETIC FIXTURE — invented numbers, for testing only"
        return (
            "BLS OES (May 2024 + May 2021) · O*NET 29.0 · "
            "BLS Employment Projections 2024-34"
        )


def resolve_source() -> tuple[Path, bool]:
    """Return (directory, is_synthetic) for whichever dataset is available."""
    real = schema.DATA_DIR / schema.TALENT_PARQUET
    if real.exists():
        return schema.DATA_DIR, False

    fixture = schema.FIXTURE_DIR / schema.TALENT_PARQUET
    if fixture.exists():
        return schema.FIXTURE_DIR, True

    raise DatasetNotFound(
        "No dataset found.\n\n"
        f"  Looked for real data at:  {real}\n"
        f"  Looked for a fixture at:  {fixture}\n\n"
        "Build the real dataset with:  python scripts/build_dataset.py\n"
        "Or a synthetic fixture with:  python scripts/make_fixture.py"
    )


def load() -> Dataset:
    """Read both Parquet files from whichever source is available."""
    source_dir, is_synthetic = resolve_source()

    talent = pd.read_parquet(source_dir / schema.TALENT_PARQUET)
    skills = pd.read_parquet(source_dir / schema.SKILLS_PARQUET)

    # Parquet round-trips dtypes faithfully, but a hand-edited or
    # externally-produced file might not. Coercing here means every downstream
    # module can assume the contract in tms.schema holds.
    talent = talent.astype(schema.TALENT_COLUMNS)
    skills = skills.astype(schema.SKILLS_COLUMNS)

    return Dataset(
        talent=talent,
        skills=skills,
        source_dir=source_dir,
        is_synthetic=is_synthetic,
    )
