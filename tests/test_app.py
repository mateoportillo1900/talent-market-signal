"""
Dashboard smoke tests.

`app.py` is presentation, so most of it is untestable by unit test — but the
failure modes that actually reached the screen in this project were not subtle
logic bugs. They were markdown rendering literally inside a raw HTML block, a
null formatting as the string "undefined", and a chart built from an empty
frame. Every one of those would have been caught by running the script once and
looking at what came out.

Streamlit's AppTest harness does exactly that: it executes the whole script,
including every `with tab:` block, against the same warehouse the app uses.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"

# The app is a Streamlit script, not an importable module, so it runs once per
# module and every test reads the same result.
APP_TIMEOUT = 120


@pytest.fixture(scope="module")
def app() -> AppTest:
    return AppTest.from_file(str(APP), default_timeout=APP_TIMEOUT).run()


def test_app_runs_without_exception(app: AppTest) -> None:
    assert not app.exception, [str(e) for e in app.exception]


def test_app_surfaces_no_errors(app: AppTest) -> None:
    """st.error means the warehouse guard tripped or a view failed."""
    assert not app.error, [e.value for e in app.error]


def test_every_view_is_present(app: AppTest) -> None:
    assert len(app.tabs) == 5


def _blocks(app: AppTest, marker: str) -> list[str]:
    """Rendered blocks containing `marker`, excluding the stylesheet.

    The CSS block names every one of these classes too, so matching on a bare
    class name would happily pass against the stylesheet and test nothing.
    """
    return [
        m.value
        for m in app.markdown
        if marker in m.value and not m.value.lstrip().startswith("<style>")
    ]


def test_findings_render_as_html_not_literal_markdown(app: AppTest) -> None:
    """The bug this exists for.

    The generated takeaways are emitted inside a raw HTML block, and Streamlit
    does no markdown processing in there — so `**Seattle**` reaches the screen
    as literal asterisks unless it has gone through `narrative.to_html`.
    """
    findings = _blocks(app, 'class="finding"')
    assert findings, "no findings rendered at all"
    for block in findings:
        assert "**" not in block, f"unconverted markdown in a finding: {block[:160]}"


def test_stat_tiles_carry_an_explanatory_note(app: AppTest) -> None:
    """A number in a box is not an insight. Every tile explains its own unit."""
    grids = _blocks(app, '<div class="stat-grid">')
    assert grids, "no stat tiles rendered"
    for grid in grids:
        assert grid.count("stat-note") == grid.count("stat-value"), (
            "a tile is missing its note"
        )


@pytest.mark.parametrize("token", ["undefined", "NaN", "nan%", "None%", "$nan"])
def test_no_placeholder_text_reaches_the_screen(app: AppTest, token: str) -> None:
    """A null that formats as text looks like a real value to a reader."""
    body = " ".join(m.value for m in app.markdown)
    assert token not in body, f"{token!r} leaked into rendered output"


def test_the_orientation_copy_is_present(app: AppTest) -> None:
    """A first-time reader should be told what they are looking at."""
    explains = _blocks(app, 'class="explain"')
    assert len(explains) >= 4, "views are missing their reading guides"
