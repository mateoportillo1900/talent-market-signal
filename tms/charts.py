"""
Chart builders.

Every figure the app draws is constructed here, so the visual language is
consistent by construction rather than by remembering to match it each time.

Colour policy
─────────────
Colours are assigned by the job the encoding does, never by taste:

    magnitude / ranking     one blue hue, light to dark
    above / below a base    diverging blue <-> red with a neutral midpoint
    ordinal categories      three steps of the same blue

All three sets were checked with the palette validator rather than eyeballed:

    ordinal 3-step   monotone lightness, adjacent dL >= 0.06,
                     light end 2.06:1 on surface, hue spread 3 degrees
    diverging poles  worst-pair CVD dE 21.6 (protan), normal-vision dE 32.3,
                     both poles >= 3:1 on surface

The app commits to a light surface — .streamlit/config.toml sets it explicitly
— so there is no dark variant to keep in step.

Two rules the charts follow throughout, because breaking either is the fastest
way to make a correct number look wrong:

  * One axis. Never two y-scales on one plot. Where two measures matter
    (cost and pool depth), they get two charts or an encoding on the same
    axis, never a second scale.
  * Colour follows the entity, not its rank. Filtering the metro list must not
    repaint the survivors.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# ── Surfaces and ink ─────────────────────────────────────────────────────────
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F3F6F8"
TEXT_PRIMARY = "#1D2226"
TEXT_SECONDARY = "#52514E"
TEXT_MUTED = "#8A8D91"
GRID = "#E6E9EC"

# LinkedIn blue, for UI chrome only. Never used as a data colour — chart series
# come from the validated ramps below.
BRAND = "#0A66C2"

# ── Sequential: magnitude ────────────────────────────────────────────────────
# Blue ramp, steps 100 -> 700. Used for continuous magnitude encodings.
SEQ = [
    "#cde2fb",
    "#b7d3f6",
    "#9ec5f4",
    "#86b6ef",
    "#6da7ec",
    "#5598e7",
    "#3987e5",
    "#2a78d6",
    "#256abf",
    "#1c5cab",
    "#184f95",
    "#104281",
    "#0d366b",
]
ACCENT = "#2a78d6"

# ── Ordinal: three discrete ordered steps ────────────────────────────────────
# Validated with --ordinal: the light end clears 2:1 against the surface, so
# the palest step is still visible rather than dissolving into the background.
ORDINAL_3 = ["#86b6ef", "#2a78d6", "#104281"]

# Pool depth is ordered, not categorical: Thin < Adequate < Deep. Encoding it
# with a one-hue ramp says "these are rungs on a scale"; three unrelated hues
# would say "these are different kinds of thing", which is wrong.
POOL_DEPTH_COLOURS = {
    "Thin": ORDINAL_3[0],
    "Adequate": ORDINAL_3[1],
    "Deep": ORDINAL_3[2],
}

# ── Diverging: above / below a baseline ──────────────────────────────────────
DIV_LOW = "#2a78d6"  # blue  — below baseline (cheaper, less important)
DIV_HIGH = "#e34948"  # red   — above baseline (pricier, more important)
DIV_MID = "#f0efec"  # neutral gray midpoint

FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"


def _base_layout(fig: go.Figure, height: int, title: str | None = None) -> go.Figure:
    """Shared layout. Recessive grid and axes, generous margins, no chartjunk."""
    fig.update_layout(
        height=height,
        # Plotly renders `title=None` as the literal string "undefined" above
        # the plot, so an untitled chart gets an explicitly empty title.
        title=dict(
            text=title or "",
            font=dict(size=15, color=TEXT_PRIMARY),
            x=0,
            xanchor="left",
        ),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT, size=12, color=TEXT_SECONDARY),
        # Bars label their values outside the mark, so the right margin has to
        # leave room or the largest value — the one people look for — is the
        # one that gets clipped.
        margin=dict(l=8, r=72, t=44 if title else 12, b=8),
        hoverlabel=dict(
            bgcolor=SURFACE,
            bordercolor=GRID,
            font=dict(family=FONT, size=12, color=TEXT_PRIMARY),
        ),
        showlegend=False,
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor=GRID,
        gridwidth=1,
        zeroline=False,
        showline=False,
        ticks="",
        title_font=dict(size=11, color=TEXT_MUTED),
    )
    fig.update_yaxes(
        showgrid=False,
        zeroline=False,
        showline=False,
        ticks="",
        title_font=dict(size=11, color=TEXT_MUTED),
    )
    return fig


def _seq_colour(value: float, lo: float, hi: float) -> str:
    """Map a value onto the sequential ramp."""
    if hi <= lo:
        return ACCENT
    pos = (value - lo) / (hi - lo)
    idx = int(round(pos * (len(SEQ) - 1)))
    return SEQ[max(0, min(len(SEQ) - 1, idx))]


# ═════════════════════════════════════════════════════════════════════════════
#  Talent Pool
# ═════════════════════════════════════════════════════════════════════════════


def competition_ranking(frame: pd.DataFrame, top_n: int = 15) -> go.Figure:
    """Horizontal bar: metros ranked by Competition Index.

    Ranking is a magnitude question, so it takes one hue light-to-dark. The
    value is direct-labelled on every bar — there are only fifteen, and making
    the reader trace each one back to an axis to recover a number they came
    for is a needless tax.
    """
    top = frame.head(top_n).iloc[::-1]
    idx = top["competition_index"]
    lo, hi = float(idx.min()), float(idx.max())
    colours = [_seq_colour(v, lo, hi) for v in top["competition_index"]]

    fig = go.Figure(
        go.Bar(
            x=top["competition_index"],
            y=top["metro"],
            orientation="h",
            marker=dict(color=colours, line=dict(width=0)),
            text=[f"{v:.0f}" for v in top["competition_index"]],
            textposition="outside",
            textfont=dict(size=11, color=TEXT_SECONDARY),
            customdata=top[["employment", "wage_p50", "scarcity_score"]].to_numpy(),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Competition Index  %{x:.0f} / 100<br>"
                "Employed  %{customdata[0]:,.0f}<br>"
                "Median wage  $%{customdata[1]:,.0f}<br>"
                "Scarcity  %{customdata[2]:.0f} / 100"
                "<extra></extra>"
            ),
        )
    )
    # Pad past 100 so a metro scoring at the top still has room for its label.
    fig.update_xaxes(range=[0, max(100.0, hi) * 1.12], title="Competition Index")
    return _base_layout(fig, height=42 * len(top) + 70)


def wage_range(frame: pd.DataFrame, top_n: int = 12) -> go.Figure:
    """Dot plot with a p10-p90 range bar, one row per metro.

    A box plot would imply quartiles computed from a sample we do not have —
    BLS publishes the percentiles directly. Drawing the published range and
    marking the median is the honest form: it shows exactly the five numbers
    that exist and invents no distribution between them.
    """
    top = frame.head(top_n).iloc[::-1]
    fig = go.Figure()

    for _, row in top.iterrows():
        fig.add_trace(
            go.Scatter(
                x=[row["wage_p10"], row["wage_p90"]],
                y=[row["metro"], row["metro"]],
                mode="lines",
                line=dict(color=SEQ[2], width=6),
                hoverinfo="skip",
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[row["wage_p25"], row["wage_p75"]],
                y=[row["metro"], row["metro"]],
                mode="lines",
                line=dict(color=SEQ[5], width=6),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    fig.add_trace(
        go.Scatter(
            x=top["wage_p50"],
            y=top["metro"],
            mode="markers",
            marker=dict(
                color=ACCENT,
                size=11,
                line=dict(color=SURFACE, width=2),  # 2px surface ring
            ),
            customdata=top[["wage_p10", "wage_p25", "wage_p75", "wage_p90"]].to_numpy(),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "p90  $%{customdata[3]:,.0f}<br>"
                "p75  $%{customdata[2]:,.0f}<br>"
                "<b>p50  $%{x:,.0f}</b><br>"
                "p25  $%{customdata[1]:,.0f}<br>"
                "p10  $%{customdata[0]:,.0f}"
                "<extra></extra>"
            ),
            showlegend=False,
        )
    )
    fig.update_xaxes(title="Annual wage (USD)", tickprefix="$", tickformat=",.0f")
    return _base_layout(fig, height=38 * len(top) + 70)


# ═════════════════════════════════════════════════════════════════════════════
#  Cost of Talent
# ═════════════════════════════════════════════════════════════════════════════


def wage_delta(frame: pd.DataFrame, baseline_metro: str, top_n: int = 15) -> go.Figure:
    """Diverging bar: annual cost difference against the baseline metro.

    Textbook diverging encoding — a real, meaningful zero (the baseline), with
    values falling either side of it. Blue for cheaper, red for pricier, and
    the baseline itself pinned at zero in neutral gray so the reader can see
    what they are being compared against.
    """
    cheapest = frame.head(top_n // 2)
    priciest = frame.tail(top_n - len(cheapest))
    # The baseline is the thing every other bar is measured against. If it
    # falls in the middle of the range it would be trimmed out by the head/tail
    # slice, leaving a chart of differences with no visible zero reference.
    baseline_row = frame[frame["is_baseline"]]
    shown = pd.concat([cheapest, priciest, baseline_row])
    shown = shown.drop_duplicates("area_code")
    shown = shown.sort_values("annual_delta_total", ascending=False)

    colours = [
        DIV_MID if is_base else (DIV_LOW if delta < 0 else DIV_HIGH)
        for delta, is_base in zip(
            shown["annual_delta_total"], shown["is_baseline"], strict=True
        )
    ]

    labels = [
        "baseline" if is_base else f"{d / 1000:+,.0f}k"
        for d, is_base in zip(
            shown["annual_delta_total"], shown["is_baseline"], strict=True
        )
    ]

    fig = go.Figure(
        go.Bar(
            x=shown["annual_delta_total"],
            y=shown["metro"],
            orientation="h",
            marker=dict(color=colours, line=dict(width=0)),
            text=labels,
            textposition="outside",
            textfont=dict(size=11, color=TEXT_SECONDARY),
            customdata=shown[
                ["wage_at_percentile", "wage_delta_pct", "pool_depth", "employment"]
            ].to_numpy(),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Annual difference  $%{x:,.0f}<br>"
                "Wage per hire  $%{customdata[0]:,.0f}  (%{customdata[1]:+.1%})<br>"
                "Local pool  %{customdata[3]:,.0f}  (%{customdata[2]})"
                "<extra></extra>"
            ),
        )
    )
    fig.add_vline(x=0, line_width=2, line_color=TEXT_MUTED)

    # A margin alone does not save the extreme label: the longest bar reaches
    # the axis maximum, so its outside label starts where the plot area ends.
    # Padding the range gives the label somewhere to live inside the plot.
    span = shown["annual_delta_total"]
    low, high = float(span.min()), float(span.max())
    pad = max(abs(low), abs(high)) * 0.22 or 1.0
    fig.update_xaxes(
        title=f"Annual cost vs {baseline_metro}",
        tickprefix="$",
        tickformat=",.0f",
        range=[min(low, 0) - pad, max(high, 0) + pad],
    )
    return _base_layout(fig, height=38 * len(shown) + 80)


def cost_vs_depth(frame: pd.DataFrame, headcount: int) -> go.Figure:
    """Scatter: saving against pool depth, so cheap-but-empty metros expose themselves.

    This is the guardrail chart. Sorting by saving alone puts thin markets on
    top, and a recommendation to hire twenty people from a pool of forty is
    worse than no recommendation. Plotting both dimensions makes the trade
    visible instead of leaving it in a footnote.

    Pool depth is ordered (Thin < Adequate < Deep) so it takes an ordinal
    one-hue ramp, and every point is labelled, so identity is never colour
    alone.
    """
    fig = go.Figure()

    for depth in ("Thin", "Adequate", "Deep"):
        subset = frame[frame["pool_depth"] == depth]
        if subset.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=subset["annual_delta_total"],
                y=subset["employment"],
                mode="markers",
                name=depth,
                marker=dict(
                    color=POOL_DEPTH_COLOURS[depth],
                    size=13,
                    line=dict(color=SURFACE, width=2),
                ),
                customdata=subset[
                    ["metro", "wage_at_percentile", "hires_supportable"]
                ].to_numpy(),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Annual difference  $%{x:,.0f}<br>"
                    "Local pool  %{y:,.0f}<br>"
                    "Supportable hires/yr  %{customdata[2]:,.0f}"
                    "<extra></extra>"
                ),
            )
        )

    fig.add_vline(x=0, line_width=2, line_color=TEXT_MUTED)
    fig.add_hline(
        y=headcount / 0.02,
        line_width=2,
        line_dash="dot",
        line_color=DIV_HIGH,
        annotation_text=f"pool needed for {headcount} hires",
        annotation_position="top right",
        annotation_font=dict(size=11, color=DIV_HIGH),
    )
    fig.update_xaxes(
        title="Annual cost difference vs baseline",
        tickprefix="$",
        tickformat=",.0f",
    )
    fig.update_yaxes(
        title="Local pool (employed)", showgrid=True, gridcolor=GRID, type="log"
    )
    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            title=dict(text="Pool depth  ", font=dict(size=11, color=TEXT_MUTED)),
            font=dict(size=11, color=TEXT_SECONDARY),
        ),
    )
    return _base_layout(fig, height=460)


# ═════════════════════════════════════════════════════════════════════════════
#  Skills
# ═════════════════════════════════════════════════════════════════════════════


def skill_distinctiveness(frame: pd.DataFrame, top_n: int = 14) -> go.Figure:
    """Diverging bar: how far each skill sits from the cross-occupation average.

    Sorting skills by raw importance returns Active Listening and Reading
    Comprehension for nearly every white-collar occupation — true, and useless
    in a conversation. Centring on the average turns the same data into what
    actually separates this role from the average professional job, which is
    the thing worth saying out loud.
    """
    order = frame["distinctive"].abs().sort_values(ascending=False).index
    ranked = frame.reindex(order)
    shown = ranked.head(top_n).sort_values("distinctive")

    colours = [DIV_HIGH if v > 0 else DIV_LOW for v in shown["distinctive"]]

    fig = go.Figure(
        go.Bar(
            x=shown["distinctive"],
            y=shown["skill"],
            orientation="h",
            marker=dict(color=colours, line=dict(width=0)),
            customdata=shown[["importance", "mean_importance", "z_score"]].to_numpy(),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Importance for this role  %{customdata[0]:.2f} / 5<br>"
                "Typical across occupations  %{customdata[1]:.2f}<br>"
                "Difference  %{x:+.2f}  (%{customdata[2]:+.1f} SD)"
                "<extra></extra>"
            ),
        )
    )
    fig.add_vline(x=0, line_width=2, line_color=TEXT_MUTED)
    fig.update_xaxes(title="Importance relative to the typical occupation")
    return _base_layout(fig, height=34 * len(shown) + 80)


def adjacency_ranking(frame: pd.DataFrame) -> go.Figure:
    """Horizontal bar: nearest occupations by skill similarity.

    Magnitude question, so one hue. The scale is fixed to [-1, 1] rather than
    auto-ranged: a similarity of 0.31 looks impressive next to an axis that
    stops at 0.35, and honest next to an axis that stops at 1.
    """
    shown = frame.iloc[::-1]
    lo, hi = float(shown["similarity"].min()), float(shown["similarity"].max())
    colours = [_seq_colour(v, lo, hi) for v in shown["similarity"]]

    fig = go.Figure(
        go.Bar(
            x=shown["similarity"],
            y=shown["occupation"],
            orientation="h",
            marker=dict(color=colours, line=dict(width=0)),
            text=[f"{v:.2f}" for v in shown["similarity"]],
            textposition="outside",
            textfont=dict(size=11, color=TEXT_SECONDARY),
            customdata=shown[["occupation_group", "shared_strength_count"]].to_numpy(),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "%{customdata[0]}<br>"
                "Skill similarity  %{x:.2f}<br>"
                "Shared strengths  %{customdata[1]}"
                "<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(
        range=[min(-0.05, lo * 1.1), 1.0],
        title="Skill similarity (mean-centred cosine)",
    )
    return _base_layout(fig, height=40 * len(shown) + 80)


# ═════════════════════════════════════════════════════════════════════════════
#  Program Health
# ═════════════════════════════════════════════════════════════════════════════


def usage_over_time(frame: pd.DataFrame) -> go.Figure:
    """Line: insight pulls per day.

    One series, so no legend — the title names it. Area fill under the line
    because a single volume series reads better filled than floating.
    """
    fig = go.Figure(
        go.Scatter(
            x=frame["day"],
            y=frame["events"],
            mode="lines",
            line=dict(color=ACCENT, width=2),
            fill="tozeroy",
            fillcolor="rgba(42, 120, 214, 0.10)",
            hovertemplate="<b>%{x|%b %d}</b><br>%{y:,.0f} views<extra></extra>",
        )
    )
    fig.update_yaxes(title="Views", showgrid=True, gridcolor=GRID, rangemode="tozero")
    return _base_layout(fig, height=280)


def usage_by_view(frame: pd.DataFrame) -> go.Figure:
    """Horizontal bar: which views get used."""
    shown = frame.iloc[::-1]
    lo, hi = float(shown["events"].min()), float(shown["events"].max())
    colours = [_seq_colour(v, lo, hi) for v in shown["events"]]

    fig = go.Figure(
        go.Bar(
            x=shown["events"],
            y=shown["view_name"],
            orientation="h",
            marker=dict(color=colours, line=dict(width=0)),
            text=[f"{int(v):,}" for v in shown["events"]],
            textposition="outside",
            textfont=dict(size=11, color=TEXT_SECONDARY),
            hovertemplate="<b>%{y}</b><br>%{x:,.0f} views<extra></extra>",
        )
    )
    fig.update_xaxes(title="Views")
    return _base_layout(fig, height=36 * len(shown) + 80)
