"""
Talent Market Signal — Streamlit dashboard.

Presentation only. Every number on screen is computed by a query in `sql/`
and reached through `tms.metrics`; nothing is calculated here. That split is
the point of the repo: the analysis is portable SQL, and this file is the part
that would be rebuilt in Tableau or anything else without touching the logic.

Two rules shape the layout:

  * The reader is not an analyst. Someone opening this has a few minutes and a
    customer conversation to prepare for, so every view leads with a sentence
    and explains how to read the chart underneath it. A chart handed to someone
    who does not already know the answer is a puzzle, not an insight.

  * One emphasis per section. The generated finding gets the accent treatment;
    orientation text is deliberately quieter. If everything is emphasised,
    nothing is.

Run:
    streamlit run app.py
"""

from __future__ import annotations

import uuid
from html import escape
from typing import NamedTuple

import streamlit as st

from tms import charts, data, metrics, narrative, schema

APP_NAME = "Talent Market Signal"
PAGE_ICON = "📍"
GITHUB_URL = "https://github.com/mateoportillo1900/talent-market-signal"

st.set_page_config(
    page_title=APP_NAME,
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": f"**{APP_NAME}** — labor-market insights on public data."},
)

st.markdown(
    """
    <style>
      /* ── Tokens ──────────────────────────────────────────────────────── */
      :root {
        --ink:        #1D2226;
        --ink-2:      #52514E;
        --ink-muted:  #767B7F;
        --line:       #E3E6E8;
        --line-soft:  #EDF0F2;
        --surface:    #FFFFFF;
        --surface-2:  #F5F7F9;
        --brand:      #0A66C2;
        --good:       #1A7F5A;
      }

      /* Streamlit chrome we do not want in a screenshot. */
      #MainMenu, footer { visibility: hidden; }
      @media (min-width: 769px) { header { visibility: hidden; } }

      .block-container { padding: 1.1rem 2.2rem 3rem 2.2rem; max-width: 1380px; }

      /* ── Type scale ──────────────────────────────────────────────────── */
      h1 { font-size: 1.7rem !important; letter-spacing: -0.021em;
           font-weight: 700; margin-bottom: 0.1rem; }
      h2 { font-size: 1.08rem !important; font-weight: 650;
           letter-spacing: -0.008em; margin: 0 0 0.15rem 0; padding-top: 0.2rem; }
      h3 { font-size: 0.95rem !important; color: var(--ink-2); font-weight: 600; }

      /* ── Title block ─────────────────────────────────────────────────── */
      .title-sub { font-size: 0.95rem; color: var(--ink-2); line-height: 1.5;
                   margin: 0.15rem 0 0.1rem 0; max-width: 72ch; }
      .title-meta { font-size: 0.78rem; color: var(--ink-muted);
                    margin: 0.5rem 0 1.15rem 0; }
      .chip { display: inline-block; padding: 0.12rem 0.5rem; border-radius: 999px;
              background: var(--surface-2); border: 1px solid var(--line);
              font-size: 0.72rem; color: var(--ink-2); font-weight: 600;
              margin-right: 0.35rem; }

      /* ── Stat tiles ──────────────────────────────────────────────────── */
      .stat-grid { display: grid;
                   grid-template-columns: repeat(auto-fit, minmax(178px, 1fr));
                   border: 1px solid var(--line); border-radius: 10px;
                   overflow: hidden; background: var(--surface);
                   margin: 0.35rem 0 1.15rem 0; }
      .stat { padding: 0.8rem 1.05rem 0.9rem 1.05rem;
              border-right: 1px solid var(--line-soft); }
      .stat:last-child { border-right: none; }
      .stat-label { font-size: 0.78rem; color: var(--ink-muted);
                    font-weight: 600; line-height: 1.3; }
      /* Proportional figures deliberately: tabular-nums makes a large
         standalone value look loose. Tabular is for columns that must align. */
      .stat-value { font-size: 1.55rem; font-weight: 660; color: var(--ink);
                    line-height: 1.15; margin-top: 0.22rem;
                    letter-spacing: -0.017em; }
      .stat-value.pos { color: var(--good); }
      .stat-note { font-size: 0.775rem; color: var(--ink-2);
                   margin-top: 0.32rem; line-height: 1.42; }

      /* ── The generated finding ───────────────────────────────────────── */
      .finding { background: var(--surface-2); border-left: 3px solid var(--brand);
                 padding: 0.85rem 1.15rem; border-radius: 0 7px 7px 0;
                 margin: 0.15rem 0 1.15rem 0; font-size: 0.945rem;
                 line-height: 1.58; color: var(--ink); }

      /* ── Orientation text ────────────────────────────────────────────── */
      .explain { font-size: 0.87rem; color: var(--ink-2); line-height: 1.55;
                 margin: 0 0 0.85rem 0; max-width: 84ch; }
      .caveat { font-size: 0.785rem; color: var(--ink-muted); line-height: 1.5;
                margin: -0.35rem 0 0.4rem 0; max-width: 92ch; }
      .caveat code, .explain code { background: var(--surface-2);
                 padding: 0.05rem 0.3rem; border-radius: 4px; font-size: 0.92em; }

      /* ── Overview: opening paragraph ─────────────────────────────────── */
      .lead { font-size: 1.0rem; color: var(--ink-2); line-height: 1.62;
              max-width: 78ch; margin: 0.2rem 0 1.15rem 0; }

      /* ── Overview: the pipeline strip ────────────────────────────────── */
      /* Numbered rather than arrowed: CSS arrows between grid cells break the
         moment the grid wraps to a second row, and this one wraps by design. */
      .pipe { display: grid;
              grid-template-columns: repeat(auto-fit, minmax(196px, 1fr));
              gap: 0.7rem; margin: 0.45rem 0 0.9rem 0; }
      .pipe-step { border: 1px solid var(--line); border-radius: 10px;
                   padding: 0.85rem 0.95rem 0.9rem 0.95rem;
                   background: var(--surface); }
      .pipe-n { width: 1.4rem; height: 1.4rem; border-radius: 999px;
                background: var(--brand); color: #FFFFFF; font-size: 0.73rem;
                font-weight: 700; display: flex; align-items: center;
                justify-content: center; margin-bottom: 0.5rem; }
      .pipe-h { font-size: 0.88rem; font-weight: 650; color: var(--ink);
                line-height: 1.3; }
      .pipe-b { font-size: 0.795rem; color: var(--ink-2); line-height: 1.47;
                margin-top: 0.28rem; }
      .pipe-t { font-size: 0.715rem; color: var(--ink-muted);
                margin-top: 0.55rem; word-break: break-all;
                font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }

      /* ── Prose measure ───────────────────────────────────────────────── */
      /* Markdown paragraphs and lists otherwise run the full width of the
         container — roughly 200 characters a line, well past the point where
         the eye loses its place returning to the left margin. Tables and
         charts are deliberately untouched; they need the width. */
      div[data-testid="stMarkdownContainer"] p,
      div[data-testid="stMarkdownContainer"] li { max-width: 86ch; }

      /* ── Section rule ────────────────────────────────────────────────── */
      .sec { margin-top: 1.9rem; padding-top: 1.15rem;
             border-top: 1px solid var(--line-soft); }

      /* ── Tabs ────────────────────────────────────────────────────────── */
      button[data-baseweb="tab"] p { font-size: 0.93rem !important;
                                     font-weight: 600; }
      div[data-baseweb="tab-list"] { gap: 1.55rem;
                                     border-bottom: 1px solid var(--line); }

      /* ── Sidebar ─────────────────────────────────────────────────────── */
      section[data-testid="stSidebar"] { border-right: 1px solid var(--line); }
      .side-brand { font-size: 1.02rem; font-weight: 700; color: var(--ink); }
      .side-tag { font-size: 0.8rem; color: var(--ink-2); line-height: 1.45;
                  margin-top: 0.2rem; }

      /* ── Footer ──────────────────────────────────────────────────────── */
      .page-foot { margin-top: 2.6rem; padding-top: 0.9rem;
                   border-top: 1px solid var(--line-soft); font-size: 0.775rem;
                   color: var(--ink-muted); line-height: 1.55; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Presentation helpers ─────────────────────────────────────────────────────


class Stat(NamedTuple):
    """One tile. `note` is what stops the number being a number in a box."""

    label: str
    value: str
    note: str = ""
    tone: str = ""  # "" or "pos"


def stat_row(stats: list[Stat]) -> None:
    """A row of tiles. Values are pre-formatted; notes explain what they mean."""
    cells = []
    for s in stats:
        note = f'<div class="stat-note">{escape(s.note)}</div>' if s.note else ""
        cells.append(
            f'<div class="stat">'
            f'<div class="stat-label">{escape(s.label)}</div>'
            f'<div class="stat-value {s.tone}">{escape(s.value)}</div>'
            f"{note}</div>"
        )
    st.markdown(
        f'<div class="stat-grid">{"".join(cells)}</div>', unsafe_allow_html=True
    )


def finding(text: str) -> None:
    """Render a generated finding in its accent box — one per section.

    Goes through `narrative.to_html` because the box is raw HTML, and Streamlit
    does not process markdown inside a raw HTML block.
    """
    st.markdown(
        f'<div class="finding">{narrative.to_html(text)}</div>',
        unsafe_allow_html=True,
    )


def explain(text: str) -> None:
    """Orientation text: what this is and how to read it. Quieter by design."""
    st.markdown(f'<p class="explain">{text}</p>', unsafe_allow_html=True)


def caveat(text: str) -> None:
    """A footnote under a chart — limits, method, what not to conclude."""
    st.markdown(f'<p class="caveat">{text}</p>', unsafe_allow_html=True)


class Stage(NamedTuple):
    """One step in the pipeline strip. `where` is the file that does it."""

    heading: str
    body: str
    where: str


def pipeline(stages: list[Stage]) -> None:
    """The extract-to-screen strip on the Overview tab.

    Numbered rather than joined by arrows: the grid wraps to a second row on a
    narrow window, and drawn connectors point the wrong way when it does.
    """
    cells = [
        f'<div class="pipe-step">'
        f'<div class="pipe-n">{i}</div>'
        f'<div class="pipe-h">{escape(s.heading)}</div>'
        f'<div class="pipe-b">{escape(s.body)}</div>'
        f'<div class="pipe-t">{escape(s.where)}</div>'
        f"</div>"
        for i, s in enumerate(stages, start=1)
    ]
    st.markdown(f'<div class="pipe">{"".join(cells)}</div>', unsafe_allow_html=True)


def section(heading: str, how_to_read: str = "") -> None:
    """A ruled section break with its heading and optional reading guide."""
    st.markdown('<div class="sec"></div>', unsafe_allow_html=True)
    st.markdown(f"## {heading}")
    if how_to_read:
        explain(how_to_read)


# ── Cached readers ───────────────────────────────────────────────────────────
# Neon's free tier idles, and Streamlit re-runs this script top to bottom on
# every widget interaction. Without caching, dragging the headcount slider
# would issue a fresh round trip per frame.


@st.cache_data(ttl=900, show_spinner=False)
def _competition(soc: str):
    return metrics.competition_index(soc)


@st.cache_data(ttl=900, show_spinner=False)
def _arbitrage(soc: str, baseline: str, headcount: int, percentile: str):
    return metrics.wage_arbitrage(soc, baseline, headcount, percentile)


@st.cache_data(ttl=900, show_spinner=False)
def _skills(soc: str):
    return metrics.skill_profile(soc)


@st.cache_data(ttl=900, show_spinner=False)
def _adjacency(soc: str, limit: int):
    return metrics.skill_adjacency(soc, limit)


@st.cache_data(ttl=900, show_spinner=False)
def _summary(soc: str, area: str):
    return metrics.talent_pool_summary(soc, area)


@st.cache_data(ttl=900, show_spinner=False)
def _metros(soc: str):
    return metrics.available_metros(soc)


@st.cache_data(ttl=60, show_spinner=False)
def _usage(days: int):
    return metrics.usage_summary(days)


@st.cache_data(ttl=3600, show_spinner=False)
def _overview():
    return metrics.mart_overview()


@st.cache_data(ttl=3600, show_spinner=False)
def _is_synthetic() -> bool:
    return data.is_synthetic()


# ── Guard: is the warehouse loaded at all? ───────────────────────────────────
try:
    data.require_mart()
except Exception as exc:  # noqa: BLE001
    st.title(f"{PAGE_ICON} {APP_NAME}")
    st.error("The warehouse is not ready.")
    st.code(str(exc))
    st.caption(
        "Load it with `make fixture load` for synthetic data, or "
        "`make build load-real` for the real BLS extract."
    )
    st.stop()

if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex[:12]


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f'<div class="side-brand">{PAGE_ICON} {APP_NAME}</div>'
        '<div class="side-tag">Where is the talent, what does it cost, '
        "and who else wants it?</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    st.caption("**1. Pick a role**")
    group = st.selectbox(
        "Occupation family",
        options=list(schema.OCCUPATION_GROUPS),
        index=list(schema.OCCUPATION_GROUPS).index("Engineering"),
    )
    occupations = schema.OCCUPATION_GROUPS[group]
    soc_code = st.selectbox(
        "Occupation",
        options=list(occupations),
        format_func=lambda s: occupations[s],
    )
    occupation = schema.SOC_TO_OCCUPATION[soc_code]

    metros = _metros(soc_code)
    metro_labels = dict(zip(metros["area_code"], metros["metro"], strict=True))

    st.caption("**2. Pick a home base**")
    baseline_area = st.selectbox(
        "Compare against",
        options=list(metro_labels),
        format_func=lambda a: metro_labels[a],
        help=(
            "Your current or HQ metro. Every cost comparison in the app is "
            "measured against this one, and it is the metro described by the "
            "figures at the top of the Talent Pool tab."
        ),
    )

    st.divider()

    with st.expander("What the terms mean"):
        st.markdown(
            """
**Competition Index** — 0–100 score for how hard a metro is to hire in.
Combines scarcity (50%), wage premium (30%) and supply growth (20%), each
converted to a percentile rank across metros first. Higher is harder.

**Scarcity** — people employed in the role per 1,000 jobs in the metro,
inverted. A thin local pool scores high.

**Wage premium** — the metro's median pay against the *national* median for
the same role. Positive means this metro pays above the national rate.

**p25 / p50 / p75** — wage percentiles. p50 is the median; a quarter of
people earn below p25 and a quarter above p75.

**Pool depth** — whether enough people work locally to support a hiring
plan, assuming one employer can realistically capture 2% of a metro's pool
in a year. Deep / Adequate / Thin.

**Skill similarity** — how closely two occupations match on O\\*NET skill
importance, after subtracting each skill's cross-occupation average. Runs
−1 to 1; above roughly 0.5 is a credible sourcing pool.

**SOC code** — the federal occupation code. `15-1252` is Software
Developers. Codes are buckets, not job titles.
"""
        )

    st.caption(f"SOC {soc_code} · {len(metros)} metros reporting")
    st.caption(f"[Source & method]({GITHUB_URL})")


if _is_synthetic():
    st.warning(
        "**Synthetic data.** This instance is running on the generated test "
        "fixture, not real BLS figures. Numbers are invented and must not be "
        "cited or screenshotted. Run `make build load-real` for real data.",
        icon="⚠️",
    )

# ── Title block ──────────────────────────────────────────────────────────────
baseline_metro = metro_labels[baseline_area]

st.title(occupation)
st.markdown(
    '<p class="title-sub">Where this role is hardest to hire, what it costs '
    "across U.S. metros, and which adjacent occupations you could realistically "
    "source from — built on public federal labour data.</p>"
    f'<div class="title-meta"><span class="chip">SOC {escape(soc_code)}</span>'
    f'<span class="chip">{escape(group)}</span>'
    f"Comparing against <b>{escape(baseline_metro)}</b> · "
    f"{len(metros)} metros reporting</div>",
    unsafe_allow_html=True,
)

tab_overview, tab_pool, tab_cost, tab_skills, tab_health = st.tabs(
    ["Overview", "Talent Pool", "Cost of Talent", "Skills & Sourcing", "Program Health"]
)


# ═════════════════════════════════════════════════════════════════════════════
#  Overview  —  the first thing anyone sees
# ═════════════════════════════════════════════════════════════════════════════
# Deliberately the landing tab. Every other view assumes you know what a
# Competition Index is and which metro the numbers are measured against; this
# one assumes nothing and is the only place that explains where the data came
# from, what was done to it, and what it will not tell you.
with tab_overview:
    scope = _overview()

    st.markdown("## What this is")
    st.markdown(
        '<p class="lead">A labour-market insights product built on public U.S. '
        "federal data. It answers the question a talent acquisition leader "
        "actually asks — <b>&ldquo;we can&rsquo;t fill this role, what do we "
        "do?&rdquo;</b> — and answers it in a sentence someone can repeat in a "
        "meeting without having opened the tool.</p>",
        unsafe_allow_html=True,
    )

    stat_row(
        [
            Stat(
                "Occupations",
                f"{int(scope['occupations'])}",
                f"across {len(schema.OCCUPATION_GROUPS)} families, "
                "picked in the sidebar",
            ),
            Stat(
                "Metro areas",
                f"{int(scope['metros'])}",
                f"in {int(scope['states'])} states, ranked against each other",
            ),
            Stat(
                "Facts in the warehouse",
                f"{int(scope['talent_rows']):,}",
                "one row per occupation × metro: employment and five wage percentiles",
            ),
            Stat(
                "Skill ratings",
                f"{int(scope['skill_rows']):,}",
                f"{int(scope['skills_tracked'])} O*NET skills scored 1-5 for "
                "every occupation",
            ),
        ]
    )

    section(
        "What you can do here",
        "Pick a role and a home metro in the sidebar, then work left to right. "
        "Each tab answers one question.",
    )
    st.markdown(
        """
| Tab | The question it answers |
|---|---|
| **Talent Pool** | Where is this role hardest to hire, and why? |
| **Cost of Talent** | What would N hires cost elsewhere — is the talent there? |
| **Skills & Sourcing** | What defines this role, and who else could do it? |
| **Program Health** | Is anyone using this? |
"""
    )
    explain(
        "<b>The blue-bordered box in each view is the point.</b> That sentence "
        "is generated from the numbers on screen and written to survive being "
        "repeated by someone who never opened the tool. The charts underneath "
        "it are the evidence, not the message."
    )
    explain(
        "If you only open one, make it <b>Skills &amp; Sourcing</b>. The first "
        "two tabs tell a customer their market is tight and expensive, which "
        "is reporting. Adjacency tells them which other occupation they could "
        "hire from instead — the only output here that changes what somebody "
        "does on Monday."
    )

    section(
        "Where the data comes from",
        "Everything is public and free. No proprietary data, no personal data, "
        "nothing scraped.",
    )
    st.markdown(
        """
| Source | Vintage | What it provides |
|---|---|---|
| **BLS OES**, metro | May 2024 | Employment and five wage percentiles |
| **BLS OES**, metro | May 2021 | Prior vintage, for three-year growth |
| **BLS OES**, national | May 2024 | The median each metro compares against |
| **O\\*NET** database | 29.0 | Skill importance, 1-5, per occupation |
| **BLS Projections** | 2024-34 | Ten-year outlook *(optional)* |
"""
    )
    caveat(
        "Every source above is <b>public domain</b> (BLS) or <b>CC BY 4.0</b> "
        "(O*NET), which is what makes any of this publishable. The "
        "Employment Projections feed is optional: if BLS moves it — they "
        "reorganise between vintages — the ten-year outlook disappears and "
        "nothing else changes."
    )
    caveat(
        "Three years between OES vintages is deliberate, not a gap. OES "
        "re-samples on a rolling three-year cycle, so comparing consecutive "
        "years compares heavily overlapping samples and understates real "
        "movement."
    )

    section(
        "How the data gets here",
        "Five stages. The boundary that matters is between stages 3 and 4: "
        "everything left of the warehouse is a one-time build, and everything "
        "right of it is a query against tables that are already correct.",
    )
    pipeline(
        [
            Stage(
                "Extract",
                "BLS workbooks and the O*NET database are downloaded once and "
                "cached, so a re-run after a parsing fix costs seconds rather "
                "than another 150 MB.",
                "scripts/build_dataset.py",
            ),
            Stage(
                "Filter and reshape",
                "~830 SOC codes narrow to the ones in scope. Suppression "
                "markers become null, never zero. Wide wage columns become one "
                "row per occupation × metro.",
                "scripts/build_dataset.py",
            ),
            Stage(
                "Load",
                "COPY into Postgres inside a single transaction. CHECK "
                "constraints reject an inverted wage percentile at the door, so "
                "a bad row never reaches a chart.",
                "scripts/load_to_postgres.py",
            ),
            Stage(
                "Query",
                "Every measure is a commented SQL file using ANSI window "
                "functions and CTEs. Nothing is computed in the application.",
                "sql/*.sql",
            ),
            Stage(
                "Present",
                "Streamlit and Plotly draw the result, and each view generates "
                "its written takeaway from the same numbers the charts use.",
                "app.py",
            ),
        ]
    )
    explain(
        "A failed load leaves the previous warehouse live and queryable rather "
        "than half-replaced. That is the deliberate trade: <b>a stale mart that "
        "is correct beats a fresh one that is wrong</b> — you can explain a "
        "delay, but you cannot un-say a number a customer has already heard."
    )

    section(
        "How the three measures are computed",
        "Each is a judgment call as much as a calculation, and each is stated as one.",
    )
    st.markdown(
        f"""
**Talent Competition Index (0-100)** — how hard a metro is to hire in.
Scarcity ({int(schema.INDEX_WEIGHTS["scarcity"] * 100)}%), wage premium
({int(schema.INDEX_WEIGHTS["wage_premium"] * 100)}%) and supply growth
({int(schema.INDEX_WEIGHTS["growth"] * 100)}%), each converted to a percentile
rank across metros *before* the weights are applied — which is what keeps the
composite bounded rather than clamped. Percentile rank, not a z-score,
because BLS employment is long-tailed enough that New York would otherwise
drag every mid-size metro into the bottom of the scale.

**Wage arbitrage** — headcount × the wage difference against your home metro,
at a percentile you choose. Base wages only: no benefits, equity or
relocation. A saving that quietly bundles assumptions cannot be checked, and
will be repeated anyway.

**Skill adjacency** — mean-centred cosine similarity over O\\*NET vectors.
Centring is the whole decision: importance is a strictly positive 1-5 scale,
so raw cosine puts every pair of occupations in a narrow high band and ranks
them by which ones score high on everything. Subtracting each skill's
cross-occupation average widens the usable range about tenfold.
"""
    )

    section(
        "The stack",
        "Chosen so the analysis outlives the tool that displays it.",
    )
    st.markdown(
        """
| Layer | What | Why this one |
|---|---|---|
| Warehouse | PostgreSQL 16 | A real planner to point at, free to host |
| Analysis | ANSI SQL — windows, CTEs | Ports to Trino or Spark unchanged |
| Access | psycopg 3 + a pool | One handshake per render, not per query |
| Pipeline | Python, pandas, Parquet | Moves and reshapes; computes no measure |
| App | Streamlit | The only layer Tableau would replace |
| Charts | Plotly | Colour assigned by encoding job |
| Tests | pytest, on real Postgres | Same loader that loads real data |
"""
    )

    section(
        "What it cannot tell you",
        "Stated here rather than only in the documentation, because a caveat "
        "that lives in a methodology file is a caveat nobody reads.",
    )
    st.markdown(
        """
- **Public data lags.** OES is a year or more behind. It describes the market
  that was, not the one you are hiring in this quarter.
- **SOC codes are not job titles.** "Software Developers" spans an enormous
  range of seniority and specialism in one bucket — which is exactly why the
  pay-spread figure is on screen rather than buried.
- **There is no company dimension.** Public data cannot say which employers
  compete for a pool, only how big and expensive it is. This is the
  most-requested thing the tool cannot do.
- **Nothing here is causal.** These are descriptive market statistics. A metro
  being expensive and a metro being hard to hire in are correlated; neither
  causes the other in any way this data can establish.
- **Adjacency is about skills, not credentials.** Two occupations sharing a
  skill profile does not mean a hiring manager, a licensing body, or a
  candidate agrees they are substitutable.
"""
    )

    section("Reading further")
    st.markdown(
        f"""
The repository carries the programme around the tool, not just the code:
a PRD organised by customer lifecycle stage, a measurement plan that opens by
admitting what cannot be attributed, a rollout plan with gate criteria that
can fail, and a methodology document naming every judgment call as one.

[{GITHUB_URL}]({GITHUB_URL})
"""
    )


# ═════════════════════════════════════════════════════════════════════════════
#  Talent Pool
# ═════════════════════════════════════════════════════════════════════════════
with tab_pool:
    data.log_usage("Talent Pool", soc_code, baseline_area, st.session_state.session_id)

    index_frame = _competition(soc_code)
    summary = _summary(soc_code, baseline_area)

    explain(
        f"The five figures below describe <b>{escape(baseline_metro)}</b> — the "
        "metro you chose in the sidebar. Everything further down compares every "
        "metro that reports this occupation."
    )

    premium = float(summary["wage_premium"])
    rank = int(summary["rank_by_size"])
    total_metros = int(summary["metros_total"])

    if rank == 1:
        rank_note = "The largest pool of any metro reporting this role."
    elif rank == total_metros:
        rank_note = f"The smallest of the {total_metros} metros reporting."
    else:
        rank_note = "Ranked by how many people are employed in the role."

    stat_row(
        [
            Stat(
                "People employed here",
                f"{summary['employment']:,.0f}",
                f"{summary['share_of_national_pool']:.1%} of everyone doing this "
                "job in the U.S.",
            ),
            Stat(
                "Median wage",
                f"${summary['wage_p50']:,.0f}",
                "Half earn more, half less. Base pay only — no bonus or equity.",
            ),
            Stat(
                "Vs national median",
                f"{premium:+.0%}",
                (
                    "Cheaper than the national rate for this role."
                    if premium < 0
                    else "You would be paying above the national rate here."
                ),
                tone="pos" if premium < 0 else "",
            ),
            Stat(
                "Pay spread, p25–p75",
                f"{summary['wage_dispersion']:.0%}",
                "Width of the middle half of pay. Wide means the code mixes "
                "seniority levels.",
            ),
            Stat("Pool size rank", f"#{rank} of {total_metros}", rank_note),
        ]
    )

    finding(narrative.pool_summary(summary))

    section(
        "Which metros are hardest to hire in?",
        "Each bar is one metro's <b>Competition Index</b> — 0 to 100, higher "
        "means harder. Hover any bar to see the three components behind the "
        "score. The ranking is what matters here, not the absolute number.",
    )
    finding(narrative.competition_summary(index_frame, occupation))
    st.plotly_chart(charts.competition_ranking(index_frame), width="stretch")
    caveat(
        "Competition Index combines scarcity (50%), wage premium (30%) and "
        "supply growth (20%), each as a percentile rank across metros. The "
        "weights are a stated judgment call, not a derived result — the "
        "reasoning is in the methodology."
    )

    section(
        "What does the market actually pay?",
        "One row per metro, showing the whole pay range rather than a single "
        "number. A wide band means the metro's market is spread out, so a "
        "median alone would mislead you about what an offer needs to be.",
    )
    st.plotly_chart(charts.wage_range(index_frame), width="stretch")
    caveat(
        "Dot is the median; the darker band spans p25–p75 and the lighter band "
        "p10–p90. These are BLS's published percentiles, not a distribution "
        "fitted from a sample."
    )

    with st.expander("See the underlying data"):
        st.caption(
            "Exactly what the chart is drawn from — one row per metro, "
            "straight out of the warehouse."
        )
        st.dataframe(
            index_frame[
                [
                    "metro",
                    "state",
                    "employment",
                    "employment_per_1k",
                    "wage_p50",
                    "wage_premium",
                    "supply_growth_3y",
                    "competition_index",
                    "difficulty_rank",
                ]
            ],
            width="stretch",
            hide_index=True,
        )


# ═════════════════════════════════════════════════════════════════════════════
#  Cost of Talent
# ═════════════════════════════════════════════════════════════════════════════
with tab_cost:
    data.log_usage(
        "Cost of Talent", soc_code, baseline_area, st.session_state.session_id
    )

    explain(
        f"What a hiring plan would cost in every other metro, measured against "
        f"<b>{escape(baseline_metro)}</b>. Set the size of the plan and how "
        "competitively you intend to pay — both change the answer, so neither "
        "is assumed for you."
    )

    controls = st.columns([1, 1, 2])
    headcount = controls[0].number_input(
        "Hires planned",
        min_value=1,
        max_value=500,
        value=20,
        step=5,
        help="Total cost scales with this, and so does whether a metro's pool "
        "is deep enough to support the plan.",
    )
    percentile = controls[1].selectbox(
        "Hiring at",
        options=["p25", "p50", "p75", "p90"],
        index=1,
        format_func=lambda p: {
            "p25": "p25 — below market",
            "p50": "p50 — market median",
            "p75": "p75 — competitive",
            "p90": "p90 — top of market",
        }[p],
        help="Which point in the local pay distribution you expect to hire at. "
        "Hiring at p75 is a different business decision from hiring at p50, so "
        "the saving is quoted at the level you actually plan to pay.",
    )

    arb = _arbitrage(soc_code, baseline_area, int(headcount), percentile)

    # The finding, not a hero number, carries the headline here: the honest
    # answer depends on the pool-depth guardrail, and that logic lives in
    # tms.narrative rather than being re-derived in the view where it could
    # drift out of step with it.
    finding(narrative.arbitrage_summary(arb, int(headcount), baseline_metro))

    section(
        f"Annual cost of {int(headcount)} hires vs {baseline_metro}",
        "Bars to the left of zero are cheaper than your home metro; bars to the "
        "right cost more. Zero is your baseline, so the length of a bar is the "
        "annual difference in total base pay.",
    )
    st.plotly_chart(charts.wage_delta(arb, baseline_metro), width="stretch")

    section(
        "Is the saving real? Cost against pool depth",
        "The cheapest metro is very often the one with the fewest people in it. "
        "This chart puts the saving next to whether the local pool could "
        "actually absorb your plan — a metro can only be a real answer if it "
        "sits above the line.",
    )
    st.plotly_chart(charts.cost_vs_depth(arb, int(headcount)), width="stretch")
    caveat(
        "Anything below the dotted line has too few people locally to absorb "
        "this hiring plan, assuming one employer can realistically capture 2% "
        "of a metro's pool in a year. That 2% is a stated judgment, not a "
        "published statistic. Base wage only — no benefits load, equity, or "
        "relocation, so this is a wage differential rather than a full "
        "cost-of-hire saving."
    )

    with st.expander("See the underlying data"):
        st.caption(
            "`hires_supportable` is 2% of local employment; `pool_depth` "
            "compares it to your plan."
        )
        st.dataframe(
            arb[
                [
                    "metro",
                    "state",
                    "wage_at_percentile",
                    "wage_delta_pct",
                    "annual_delta_total",
                    "employment",
                    "hires_supportable",
                    "pool_depth",
                ]
            ],
            width="stretch",
            hide_index=True,
        )


# ═════════════════════════════════════════════════════════════════════════════
#  Skills & Sourcing
# ═════════════════════════════════════════════════════════════════════════════
with tab_skills:
    data.log_usage("Skills & Sourcing", soc_code, None, st.session_state.session_id)

    explain(
        "If a role cannot be filled from its own pool, the next question is who "
        "else could do the work. This tab answers it from skill profiles rather "
        "than job titles — first what makes the role distinctive, then which "
        "occupations share that shape."
    )

    profile = _skills(soc_code)
    finding(narrative.skill_summary(profile, occupation))

    section(
        "What makes this role distinct",
        "Not the skills that matter most in absolute terms — the ones that "
        "matter <i>more here than in other occupations</i>. Bars to the right "
        "are above the cross-occupation average, bars to the left below it.",
    )
    st.plotly_chart(charts.skill_distinctiveness(profile), width="stretch")
    caveat(
        "Distance from the average importance of that skill across all 63 "
        "occupations. Ranking by raw score instead would return Active "
        "Listening and Reading Comprehension for almost every white-collar "
        "role — true, and useless in a customer conversation."
    )

    section(
        "Where else could you source from?",
        "Occupations ranked by how closely their skill profile matches this "
        "one. A high score means the two roles are unusual in the <i>same "
        "direction</i> — that is what makes a reskilling or sourcing pitch "
        "credible rather than merely arithmetic.",
    )
    limit = st.slider(
        "Occupations to compare",
        5,
        20,
        8,
        help="How far down the ranked list to show.",
    )
    adjacent = _adjacency(soc_code, limit)
    finding(narrative.adjacency_summary(adjacent, occupation))
    st.plotly_chart(charts.adjacency_ranking(adjacent), width="stretch")
    caveat(
        "Mean-centred cosine similarity over O*NET skill vectors. Centring "
        "matters: raw cosine over strictly-positive vectors compresses every "
        "occupation pair into a narrow band, making the ranking meaningless. "
        "Adjacency is about skills, not credentials — it does not mean a "
        "hiring manager or a licensing body agrees the two are substitutable."
    )

    with st.expander("See the underlying data"):
        st.caption(
            "`shared_strengths` lists the skills where both occupations sit "
            "above the cross-occupation average."
        )
        st.dataframe(
            adjacent[
                [
                    "occupation",
                    "occupation_group",
                    "similarity",
                    "shared_strength_count",
                    "shared_strengths",
                ]
            ],
            width="stretch",
            hide_index=True,
        )


# ═════════════════════════════════════════════════════════════════════════════
#  Program Health
# ═════════════════════════════════════════════════════════════════════════════
with tab_health:
    st.markdown("## Is anyone actually using this?")
    explain(
        "An insights programme that cannot answer that question has no way to "
        "earn its next quarter of investment. Every view in this app logs a "
        "row; this tab reads them back. It is deliberately small — see the "
        "note at the bottom for why."
    )

    window = st.columns([1, 3])[0].selectbox(
        "Window",
        [7, 30, 90],
        index=1,
        format_func=lambda d: f"Last {d} days",
        help="Usage is logged per view. A short window shows whether people "
        "came back; a long one shows total reach.",
    )
    usage = _usage(int(window))

    total = int(usage["by_view"]["events"].sum()) if not usage["by_view"].empty else 0
    stat_row(
        [
            Stat(
                "Views", f"{total:,}", f"Charts opened in the last {int(window)} days."
            ),
            Stat(
                "Distinct sessions",
                f"{usage['sessions']:,}",
                "Separate visits. Closer to 'people' than views are.",
            ),
            Stat(
                "Occupations explored",
                f"{usage['occupations']:,}",
                "Breadth of demand — narrow means depth beats catalogue size.",
            ),
        ]
    )

    finding(narrative.usage_summary(usage["by_view"], total, int(window)))

    if total:
        left, right = st.columns([3, 2])
        with left:
            st.markdown("### Views per day")
            st.plotly_chart(charts.usage_over_time(usage["by_day"]), width="stretch")
        with right:
            st.markdown("### By view")
            st.plotly_chart(charts.usage_by_view(usage["by_view"]), width="stretch")

        st.markdown("### Most requested")
        explain(
            "What people look up decides where the next depth investment goes. "
            "If one occupation family is most of the demand, the rest of the "
            "catalogue is breadth nobody asked for."
        )
        st.dataframe(usage["top_requests"], width="stretch", hide_index=True)
    else:
        st.info(
            "No usage logged in this window yet. Open a few views and they will "
            "appear here.",
            icon="📭",
        )

    caveat(
        "This is the honest, small version of what the measurement question "
        "really requires. <b>Adoption counts tell you a tool is being opened, "
        "not that a decision changed.</b> Building an impressive-looking impact "
        "dashboard on top of this data would be the most misleading thing in "
        "the project. See <code>docs/MEASUREMENT.md</code> for the attribution "
        "problem and what would actually be needed to claim impact."
    )


st.markdown(
    '<div class="page-foot">'
    f"{APP_NAME} · Built on BLS OES and O*NET, both public domain or CC BY · "
    f'<a href="{GITHUB_URL}">Source and method</a>'
    "</div>",
    unsafe_allow_html=True,
)
