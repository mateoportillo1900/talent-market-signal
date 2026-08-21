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


def test_overview_diagrams_render_as_svg(app: AppTest) -> None:
    """The Overview leads with two diagrams instead of walls of prose.

    Inline SVG rather than an image file or a diagram library: nothing to
    install on a deploy, and nothing that can 404. These assert both are
    present and carry an accessible title, since a diagram with no text
    alternative is a blank box to a screen reader.
    """
    svgs = [b for b in _blocks(app, "<svg") if "viewBox" in b]
    assert len(svgs) == 2, f"expected two diagrams, found {len(svgs)}"
    for svg in svgs:
        assert 'role="img"' in svg, "diagram is not exposed as an image"
        assert "<title" in svg, "diagram has no accessible title"

    flow = next((s for s in svgs if "Postgres mart" in s), None)
    assert flow, "the source-to-dashboard flow diagram is missing"
    for stage in ("BLS OES", "O*NET", "Build", "SQL queries", "This dashboard"):
        assert stage in flow, f"the flow diagram does not show {stage!r}"


def test_index_diagram_weights_match_the_schema(app: AppTest) -> None:
    """The drawn weights must be the weights the SQL actually applies.

    A diagram is the most quotable thing on the page and the least likely to
    be re-checked, so a hand-drawn 50/30/20 that drifts from the schema would
    be repeated in an interview long after the code changed.
    """
    from tms import schema  # noqa: PLC0415

    svgs = [b for b in _blocks(app, "<svg") if "Competition Index" in b]
    assert svgs, "the Competition Index diagram is missing"
    diagram = svgs[0]

    for weight in schema.INDEX_WEIGHTS.values():
        assert f"{int(weight * 100)}%" in diagram, (
            f"the diagram does not show the {weight:.0%} weight in the schema"
        )


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
    overview_grid = next((g for g in grids if "Skill ratings" in g), None)
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
    customer, and these are the ones that get a claim walked back. They stay
    on the face of the Overview rather than inside an expander for the same
    reason.
    """
    body = _overview_text(app)
    for limit in ("Public data lags", "no company dimension", "not job titles"):
        assert limit in body, f"the limit {limit!r} is not stated in the app"


def test_the_app_compiles_without_deprecated_escapes() -> None:
    """`\\*` in a normal string is a deprecated escape, and a future SyntaxError.

    This has bitten this file three times: the markdown in the app needs a
    literal backslash-asterisk to escape O*NET, and writing it with one
    backslash still works today while emitting a DeprecationWarning nobody
    reads. Ruff does not flag it. Compiling with warnings promoted to errors
    does, which is the only reason it gets caught before Python 3.12+ turns it
    into a hard failure.
    """
    import warnings  # noqa: PLC0415

    source = APP.read_text(encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        warnings.simplefilter("error", SyntaxWarning)
        compile(source, str(APP), "exec")


def test_diagrams_are_not_rendered_as_code_blocks(app: AppTest) -> None:
    """The bug this exists for, and it is invisible to every other test.

    Streamlit runs markdown before honouring `unsafe_allow_html`, so any line
    of an inline SVG indented four spaces becomes a fenced code block and the
    diagram reaches the screen as its own source. Every assertion about the
    SVG's *content* still passes while the page is visibly broken.
    """
    for svg in (b for b in _blocks(app, "<svg") if "viewBox" in b):
        first = svg.lstrip("\n").split("\n")[0]
        assert not first.startswith("    "), (
            "an SVG block starts indented, so markdown will render it as code"
        )
        assert "\n" not in svg.strip(), (
            "an SVG block spans multiple lines; indented lines become code"
        )
