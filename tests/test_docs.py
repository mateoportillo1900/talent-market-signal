"""
Documentation contract tests.

Documentation rots differently from code: nothing crashes. A link to a renamed
file, a diagram left half-fenced, a document with no owner — none of these break
a build, and all of them are found by the reader rather than by the author.

These tests are cheap and they run in CI alongside everything else, so the docs
carry the same guarantee the SQL does.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

# Every markdown file that is part of the published documentation set.
MARKDOWN = sorted([ROOT / "README.md", *DOCS.glob("*.md")])

# The programme documents — README.md in docs/ is an index, not one of them.
PROGRAM_DOCS = sorted(p for p in DOCS.glob("*.md") if p.name != "README.md")

# Markdown links that point at a path rather than an external URL or a
# pure-anchor jump within the same page.
LINK = re.compile(r"\[[^\]]*\]\((?!https?://|#|mailto:)([^)]+)\)")


def _ids(paths: list[Path]) -> list[str]:
    return [str(p.relative_to(ROOT)) for p in paths]


@pytest.mark.parametrize("path", MARKDOWN, ids=_ids(MARKDOWN))
def test_every_relative_link_resolves(path: Path) -> None:
    """No dead links. The most common documentation defect, and invisible."""
    broken = []
    for target in LINK.findall(path.read_text(encoding="utf-8")):
        # Strip any #anchor; we are checking the file exists, not the heading.
        file_part = target.split("#")[0]
        if not file_part:
            continue
        if not (path.parent / file_part).resolve().exists():
            broken.append(target)
    assert not broken, f"{path.name} links to missing paths: {broken}"


@pytest.mark.parametrize("path", MARKDOWN, ids=_ids(MARKDOWN))
def test_mermaid_fences_are_balanced(path: Path) -> None:
    """An unclosed fence swallows the rest of the document on GitHub."""
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    depth = 0
    for line in lines:
        if line.startswith("```"):
            depth = 0 if depth else 1
    assert depth == 0, f"{path.name} has an unclosed code fence"


@pytest.mark.parametrize("path", PROGRAM_DOCS, ids=_ids(PROGRAM_DOCS))
def test_every_program_doc_names_an_owner_and_a_date(path: Path) -> None:
    """A programme document nobody owns is a document nobody maintains."""
    head = path.read_text(encoding="utf-8")[:400]
    assert "**Owner:**" in head, f"{path.name} does not name an owner"
    assert "**Last updated:**" in head, f"{path.name} has no last-updated date"


@pytest.mark.parametrize("path", PROGRAM_DOCS, ids=_ids(PROGRAM_DOCS))
def test_every_program_doc_carries_a_diagram(path: Path) -> None:
    """The docs are meant to be skimmable. Prose alone is not."""
    assert "```mermaid" in path.read_text(encoding="utf-8"), (
        f"{path.name} has no diagram"
    )


@pytest.mark.parametrize("path", PROGRAM_DOCS, ids=_ids(PROGRAM_DOCS))
def test_every_program_doc_links_back_to_the_index(path: Path) -> None:
    """Landing on a document from a search result should not be a dead end."""
    assert "(./README.md)" in path.read_text(encoding="utf-8"), (
        f"{path.name} has no navigation footer"
    )


def test_the_index_lists_every_program_doc() -> None:
    """A document missing from the index is a document nobody finds."""
    index = (DOCS / "README.md").read_text(encoding="utf-8")
    missing = [
        p.name for p in PROGRAM_DOCS if f"({p.name})" not in index.replace("./", "")
    ]
    assert not missing, f"docs/README.md does not link: {missing}"


def test_diagram_export_names_do_not_collide() -> None:
    """Two diagrams resolving to one filename would silently overwrite."""
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import export_diagrams  # noqa: PLC0415

    names = [d.filename for d in export_diagrams.collect()]
    assert len(names) == len(set(names)), f"colliding diagram filenames: {names}"
    assert names, "no diagrams found to export"
