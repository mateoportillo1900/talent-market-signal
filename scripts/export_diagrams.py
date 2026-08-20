"""
Render every Mermaid diagram in the docs as a PNG.

Why this exists: GitHub renders Mermaid inline, so the documents themselves need
no image files — and a diagram that lives in a fenced code block shows up in a
diff as changed *logic* rather than as a changed binary blob. But LinkedIn,
Google Slides, Notion and PDF exports all render nothing at all. When a diagram
needs to leave the repository, it has to become a picture.

Filenames are derived from the heading each diagram sits under, numbered in
document order. Adding a diagram therefore requires no edit here — the failure
mode of a hand-maintained list is that it silently stops matching the docs.

Where a heading makes a poor filename, put an override immediately above the
fence and the diagram takes that name instead:

    <!-- diagram: lifecycle-stages -->
    ```mermaid

Usage:
    python scripts/export_diagrams.py --check    # list what would be rendered
    python scripts/export_diagrams.py            # render to docs/images/

Rendering uses Kroki (https://kroki.io), which takes the raw Mermaid source as a
POST body and returns the PNG. No account, no key, no local Chromium — but it
does need outbound network, and it is the only step in this repository that
talks to a third-party service.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
IMAGES_DIR = DOCS / "images"

KROKI_URL = "https://kroki.io/mermaid/png"
TIMEOUT = 60

# Scanned in this order; the numeric prefix on each filename follows it.
SOURCES = [
    ROOT / "README.md",
    DOCS / "PRD.md",
    DOCS / "METHODOLOGY.md",
    DOCS / "DATA_QUALITY.md",
    DOCS / "MEASUREMENT.md",
    DOCS / "GTM_ENABLEMENT.md",
    DOCS / "STAKEHOLDER_MAP.md",
    DOCS / "AI_ASSISTED_DEVELOPMENT.md",
]


class Diagram:
    """One Mermaid block, and where it came from."""

    def __init__(
        self,
        source_file: Path,
        heading: str,
        index: int,
        body: str,
        override: str | None = None,
    ):
        self.source_file = source_file
        self.heading = heading
        self.index = index
        self.body = body
        self.override = override

    @property
    def slug(self) -> str:
        """A filename-safe name: the override if given, else the heading."""
        text = (self.override or self.heading).lower()
        text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
        return text or "diagram"

    @property
    def filename(self) -> str:
        return f"{self.index:02d}-{self.slug}.png"


NAME_OVERRIDE = re.compile(r"<!--\s*diagram:\s*([a-zA-Z0-9._-]+)\s*-->")


def extract(path: Path) -> list[tuple[str, str, str | None]]:
    """Pull out every ```mermaid block, paired with its nearest heading above.

    Returns (heading, body, override) in document order.
    """
    found: list[tuple[str, str, str | None]] = []
    heading = path.stem
    override: str | None = None
    in_block = False
    current: list[str] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()

        if stripped == "```mermaid":
            in_block = True
            current = []
            continue

        if in_block:
            if stripped == "```":
                found.append((heading, "\n".join(current), override))
                override = None
                in_block = False
            else:
                current.append(line)
            continue

        match = NAME_OVERRIDE.match(stripped)
        if match:
            override = match.group(1)
            continue

        if stripped.startswith("#"):
            # Track the most recent heading so the diagram inherits its name.
            heading = stripped.lstrip("#").strip()
            # Drop trailing parentheticals and inline code ticks.
            heading = heading.replace("`", "").split("(")[0].strip()

    return found


def collect() -> list[Diagram]:
    diagrams: list[Diagram] = []
    counter = 1
    for path in SOURCES:
        if not path.exists():
            print(f"  ! missing, skipped: {path.relative_to(ROOT)}")
            continue
        for heading, body, override in extract(path):
            diagrams.append(Diagram(path, heading, counter, body, override))
            counter += 1
    return diagrams


def render(diagram: Diagram) -> None:
    response = requests.post(
        KROKI_URL,
        data=diagram.body.encode("utf-8"),
        headers={"Content-Type": "text/plain"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    out = IMAGES_DIR / diagram.filename
    out.write_bytes(response.content)
    size_kb = len(response.content) / 1024
    print(f"  ok   {diagram.filename}  ({size_kb:.0f} KB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="list the diagrams that would be rendered, without network access",
    )
    args = parser.parse_args()

    diagrams = collect()
    if not diagrams:
        print("No Mermaid diagrams found.")
        return 1

    print(f"Found {len(diagrams)} diagrams:\n")
    for d in diagrams:
        print(f"  {d.filename:<44} {d.source_file.relative_to(ROOT)} — {d.heading}")

    clashes = {d.filename for d in diagrams}
    if len(clashes) != len(diagrams):
        print("\nFilename collision — two diagrams resolved to the same name.")
        return 1

    if args.check:
        print("\n--check: nothing rendered.")
        return 0

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nRendering via {KROKI_URL} ...\n")
    failures = 0
    for d in diagrams:
        try:
            render(d)
        except requests.RequestException as exc:
            failures += 1
            print(f"  FAIL {d.filename}: {exc}")

    print(
        f"\n{len(diagrams) - failures}/{len(diagrams)} written to "
        f"{IMAGES_DIR.relative_to(ROOT)}/"
    )
    if failures:
        print("Kroki is a third-party service; a failure here is usually network,")
        print("not a broken diagram. Re-run, or check the source renders on GitHub.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
