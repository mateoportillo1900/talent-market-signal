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


def test_overview_is_the_landing_tab(app: AppTest) -> None:
    """Streamlit opens the first tab, so first is not a cosmetic ordering.

    Every other view assumes the reader knows what a Competition Index is and
    which metro the figures are measured against. Overview assumes nothing, so
    it has to be the one that opens.
    """
    labels = [tab.label for tab in app.tabs]
    assert labels[0] == "Overview", f"tab order is {labels}"


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


# ── Overview ─────────────────────────────────────────────────────────────────
# The tab a first-time reader lands on. These check that it still says what it
# is supposed to say, because it is the one view whose entire job is copy.


def _overview_text(app: AppTest) -> str:
    """Everything rendered, as one string. Cheap, and enough for presence."""
    return " ".join(m.value for m in app.markdown)


@pytest.mark.parametrize(
    "source",
    ["BLS OES", "O\\*NET", "Employment Projections", "public domain", "CC BY"],
)
def test_overview_names_its_sources(app: AppTest, source: str) -> None:
    """A dashboard that does not say where its numbers came from is a rumour."""
    assert source in _overview_text(app), f"{source!r} is not named anywhere"


def test_overview_shows_every_pipeline_stage(app: AppTest) -> None:
    """Extract to screen, with the file that does each step."""
    strips = _blocks(app, '<div class="pipe">')
    assert len(strips) == 1, "expected exactly one pipeline strip"
    strip = strips[0]
    assert strip.count('class="pipe-step"') == 5, "a pipeline stage went missing"
    for script in (
        "scripts/build_dataset.py",
        "scripts/load_to_postgres.py",
        "sql/*.sql",
        "app.py",
    ):
        assert script in strip, f"the strip does not say where {script} runs"


def test_overview_scope_figures_come_from_the_warehouse(app: AppTest) -> None:
    """The reason `sql/mart_overview.sql` exists.

    Scope described in hardcoded copy stops being true the first time the
    dataset is rebuilt — the fixture reports 40 metros and the real BLS extract
    reports far more. This asserts the rendered tiles agree with the database
    rather than with a number somebody typed.
    """
    from tms import metrics  # noqa: PLC0415

    scope = metrics.mart_overview()
    grids = _blocks(app, '<div class="stat-grid">')
    overview_grid = next((g for g in grids if "Facts in the warehouse" in g), None)
    assert overview_grid, "the Overview scope tiles are missing"

    for value in (
        f"{int(scope['occupations'])}",
        f"{int(scope['metros'])}",
        f"{int(scope['talent_rows']):,}",
        f"{int(scope['skill_rows']):,}",
    ):
        assert value in overview_grid, f"{value} is not on screen"


def test_overview_states_the_limits(app: AppTest) -> None:
    """The caveats live in the app, not only in the methodology document.

    A limit that only a reader of `docs/` ever sees is a limit that reaches no
    customer, and these are the ones that get a claim walked back.
    """
    body = _overview_text(app)
    for limit in ("Public data lags", "no company dimension", "not job titles"):
        assert limit in body, f"the limit {limit!r} is not stated in the app"
