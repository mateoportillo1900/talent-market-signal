"""
Talent Market Signal — Streamlit dashboard.

Presentation only. Every number on screen is computed by a query in `sql/`
and reached through `tms.metrics`; nothing is calculated here. That split is
the point of the repo: the analysis is portable SQL, and this file is the part
that would be rebuilt in Tableau or anything else without touching the logic.

Run:
    streamlit run app.py
"""

from __future__ import annotations

import uuid

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
      #MainMenu, footer { visibility: hidden; }
      @media (min-width: 769px) { header { visibility: hidden; } }
      .block-container { padding: 1.4rem 2rem 2rem 2rem; max-width: 1400px; }
      h1 { font-size: 1.65rem !important; letter-spacing: -0.02em; }
      h2 { font-size: 1.15rem !important; margin-top: 0.4rem; }
      h3 { font-size: 0.95rem !important; color: #52514E; font-weight: 600; }
      /* Takeaway line above each chart cluster — the sentence, not the chart,
         is what a reader carries away, so it gets the visual weight. */
      .takeaway {
        background: #F3F6F8;
        border-left: 3px solid #0A66C2;
        padding: 0.85rem 1.1rem;
        border-radius: 0 6px 6px 0;
        margin: 0.2rem 0 1.4rem 0;
        font-size: 0.95rem;
        line-height: 1.55;
        color: #1D2226;
      }
      .caveat { font-size: 0.8rem; color: #8A8D91; margin-top: -0.6rem; }
      div[data-testid="stMetricValue"] { font-size: 1.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def takeaway(text: str) -> None:
    """Render a generated finding in its styled box.

    Goes through `narrative.to_html` because the box is raw HTML, and Streamlit
    does not process markdown inside a raw HTML block.
    """
    st.markdown(
        f'<div class="takeaway">{narrative.to_html(text)}</div>',
        unsafe_allow_html=True,
    )


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
def _is_synthetic() -> bool:
    return data.is_synthetic()


# ── Guard: is the warehouse loaded at all? ───────────────────────────────────
try:
    data.require_mart()
except Exception as exc:  # noqa: BLE001
    st.title(f"{PAGE_ICON} {APP_NAME}")
    st.error("The warehouse is not ready.")
    st.code(str(exc))
    st.stop()

if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex[:12]


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### {PAGE_ICON} {APP_NAME}")
    st.caption("Where is the talent, what does it cost, and who else wants it?")
    st.divider()

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
    baseline_area = st.selectbox(
        "Compare against",
        options=list(metro_labels),
        format_func=lambda a: metro_labels[a],
        help="Your current or HQ metro. Cost comparisons are measured from here.",
    )

    st.divider()
    st.caption(f"SOC {soc_code} · {len(metros)} metros reporting")
    st.caption(f"[Source & method]({GITHUB_URL})")


if _is_synthetic():
    st.warning(
        "**Synthetic data.** This instance is running on the generated test "
        "fixture, not real BLS figures. Numbers are invented and must not be "
        "cited or screenshotted. Run `scripts/build_dataset.py` for real data.",
        icon="⚠️",
    )

st.title(f"{occupation}")

tab_pool, tab_cost, tab_skills, tab_health, tab_about = st.tabs(
    ["Talent Pool", "Cost of Talent", "Skills & Sourcing", "Program Health", "About"]
)


# ═════════════════════════════════════════════════════════════════════════════
#  Talent Pool
# ═════════════════════════════════════════════════════════════════════════════
with tab_pool:
    data.log_usage("Talent Pool", soc_code, baseline_area, st.session_state.session_id)

    index_frame = _competition(soc_code)
    summary = _summary(soc_code, baseline_area)

    left, mid, right, far = st.columns(4)
    left.metric("Employed here", f"{summary['employment']:,.0f}")
    mid.metric("Median wage", f"${summary['wage_p50']:,.0f}")
    right.metric(
        "Vs national median",
        f"{summary['wage_premium']:+.0%}",
        help="This metro's median pay against the national median for the role.",
    )
    far.metric(
        "Pool size rank",
        f"#{int(summary['rank_by_size'])} of {int(summary['metros_total'])}",
    )

    takeaway(narrative.pool_summary(summary))

    st.subheader("Which metros are hardest to hire in?")
    takeaway(narrative.competition_summary(index_frame, occupation))
    st.plotly_chart(charts.competition_ranking(index_frame), width="stretch")
    st.markdown(
        '<p class="caveat">Competition Index combines scarcity (50%), wage '
        "premium (30%) and supply growth (20%), each as a percentile rank "
        "across metros. Hover any bar for the components.</p>",
        unsafe_allow_html=True,
    )

    st.subheader("What does the market actually pay?")
    st.plotly_chart(charts.wage_range(index_frame), width="stretch")
    st.markdown(
        '<p class="caveat">Dot is the median; the darker band spans p25–p75 '
        "and the lighter band p10–p90. These are BLS's published percentiles, "
        "not a distribution fitted from a sample.</p>",
        unsafe_allow_html=True,
    )

    with st.expander("See the data"):
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

    controls = st.columns([1, 1, 2])
    headcount = controls[0].number_input(
        "Hires planned", min_value=1, max_value=500, value=20, step=5
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
    )

    arb = _arbitrage(soc_code, baseline_area, int(headcount), percentile)
    baseline_metro = metro_labels[baseline_area]

    takeaway(narrative.arbitrage_summary(arb, int(headcount), baseline_metro))

    st.subheader(f"Annual cost of {int(headcount)} hires vs {baseline_metro}")
    st.plotly_chart(charts.wage_delta(arb, baseline_metro), width="stretch")

    st.subheader("Is the saving real? Cost against pool depth")
    st.plotly_chart(charts.cost_vs_depth(arb, int(headcount)), width="stretch")
    st.markdown(
        '<p class="caveat">Anything below the dotted line has too few people '
        "locally to absorb this hiring plan, assuming one employer can "
        "realistically capture 2% of a metro's pool in a year. Base wage only "
        "— no benefits load, equity, or relocation.</p>",
        unsafe_allow_html=True,
    )

    with st.expander("See the data"):
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

    profile = _skills(soc_code)
    takeaway(narrative.skill_summary(profile, occupation))

    st.subheader("What makes this role distinct")
    st.plotly_chart(charts.skill_distinctiveness(profile), width="stretch")
    st.markdown(
        '<p class="caveat">Distance from the average importance of that skill '
        "across all 63 occupations. Red sits above the average, blue below. "
        "Ranking by raw score instead would return Active Listening for almost "
        "every white-collar role.</p>",
        unsafe_allow_html=True,
    )

    st.divider()
    limit = st.slider("Occupations to compare", 5, 20, 8)
    adjacent = _adjacency(soc_code, limit)

    takeaway(narrative.adjacency_summary(adjacent, occupation))

    st.subheader("Where else could you source from?")
    st.plotly_chart(charts.adjacency_ranking(adjacent), width="stretch")
    st.markdown(
        '<p class="caveat">Mean-centred cosine similarity over O*NET skill '
        "vectors. Centring matters: raw cosine over strictly-positive vectors "
        "compresses every occupation pair into a narrow band, making the "
        "ranking meaningless.</p>",
        unsafe_allow_html=True,
    )

    with st.expander("See the data"):
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
    st.markdown(
        "#### Is anyone actually using this?\n"
        "An insights programme that cannot answer that question has no way to "
        "earn its next quarter of investment. Every view logs a row; this tab "
        "reads them back."
    )

    window = st.selectbox(
        "Window", [7, 30, 90], index=1, format_func=lambda d: f"Last {d} days"
    )
    usage = _usage(int(window))

    total = int(usage["by_view"]["events"].sum()) if not usage["by_view"].empty else 0
    cols = st.columns(3)
    cols[0].metric("Views", f"{total:,}")
    cols[1].metric("Distinct sessions", f"{usage['sessions']:,}")
    cols[2].metric("Occupations explored", f"{usage['occupations']:,}")

    takeaway(narrative.usage_summary(usage["by_view"], total, int(window)))

    if total:
        left, right = st.columns([3, 2])
        with left:
            st.subheader("Views per day")
            st.plotly_chart(charts.usage_over_time(usage["by_day"]), width="stretch")
        with right:
            st.subheader("By view")
            st.plotly_chart(charts.usage_by_view(usage["by_view"]), width="stretch")

        st.subheader("Most requested")
        st.dataframe(usage["top_requests"], width="stretch", hide_index=True)

    st.markdown(
        '<p class="caveat">This is the honest, small version of what the '
        "measurement question really requires. Adoption counts tell you a tool "
        "is being opened, not that a decision changed. See "
        "<code>docs/MEASUREMENT.md</code> for the attribution problem and what "
        "would actually be needed to claim impact.</p>",
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════════════════════
#  About
# ═════════════════════════════════════════════════════════════════════════════
with tab_about:
    st.markdown(
        f"""
### What this is

A labour-market insights product built on public U.S. data, to demonstrate the
shape of work an insights team does: own a dataset, query it, surface it, and
measure whether anyone acts on it.

**The question it answers:** where is the talent for a role, what does it cost,
and who else is competing for it.

### Where the numbers come from

| Source | What it gives |
|---|---|
| **BLS OES** (2024, 2021) | Employment + wage percentiles by occupation × metro |
| **O\\*NET 29.0** | Skill importance ratings per occupation |
| **BLS Employment Projections** 2024–34 | Ten-year national outlook per occupation |

All public domain, all federal. No proprietary or personal data anywhere.

### How it's built

Postgres holds a `mart` schema with two tables and a usage log. Every
analytical measure is a file in `sql/` using ANSI window functions and CTEs, so
the same logic ports to Trino, Spark SQL or Snowflake unchanged. Python binds
parameters and hands back DataFrames; it computes nothing. Streamlit and Plotly
draw the result.

Data quality is enforced at load: `CHECK` constraints reject a wage-percentile
inversion or an off-scale O\\*NET rating before it can reach a chart, and the
load runs in one transaction so a failure leaves the previous mart intact.

### What it cannot tell you

- **Public data lags.** OES is a year or more behind. It describes the market
  that was, not the one you are hiring in this quarter.
- **SOC codes are not job titles.** "Software Developers" spans a huge range of
  seniority and specialism in one bucket, which is why the wage dispersion
  figure is on screen rather than buried.
- **There is no company dimension.** Public data cannot tell you which
  employers compete for a pool — only how big and expensive it is.
- **Nothing here is causal.** These are descriptive market statistics.

### Source

[{GITHUB_URL}]({GITHUB_URL})
"""
    )
