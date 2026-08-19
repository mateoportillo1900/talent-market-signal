"""
Plain-English takeaways.

Charts show; sentences tell. Every view in the app pairs its figures with a
generated sentence naming what the reader should take away, because a chart
handed to someone who does not already know the answer is a puzzle, not an
insight.

These are deterministic templates over the numbers, not a language model. That
is deliberate:

  * No API key, so the deployed app needs one secret instead of two.
  * The same data always produces the same sentence, so a screenshot taken
    today still matches the app next week.
  * They are testable. A generated claim that contradicts its own chart is
    exactly the kind of error that destroys trust in everything else on the
    page, and `tests/test_narrative.py` asserts the direction words agree with
    the sign of the number they describe.

Hedging is built in rather than bolted on: where a figure rests on imputed or
suppressed data, the sentence says so instead of asserting a clean number.
"""

from __future__ import annotations

import html
import re
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd


def _plural(n: float, singular: str, plural: str | None = None) -> str:
    return singular if round(n) == 1 else (plural or f"{singular}s")


def _round_half_up(value: float, places: int = 0) -> float:
    """Round half away from zero, the way people expect money to round.

    Python and IEEE 754 both round half to even, so $12,500 formats as "$12k"
    and $13,500 as "$14k" — inconsistent-looking in a sentence a customer
    reads, and hard to defend when someone checks the arithmetic.
    """
    quantum = Decimal(1).scaleb(-places)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def _money(value: float) -> str:
    """Round money to a scale a person would actually say out loud."""
    magnitude = abs(value)
    if magnitude >= 1_000_000:
        return f"${_round_half_up(value / 1_000_000, 1):,.1f}M"
    if magnitude >= 10_000:
        return f"${_round_half_up(value / 1_000):,.0f}k"
    return f"${_round_half_up(value):,.0f}"


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# ═════════════════════════════════════════════════════════════════════════════
#  Talent Pool
# ═════════════════════════════════════════════════════════════════════════════


def competition_summary(frame: pd.DataFrame, occupation: str) -> str:
    """Name the hardest and easiest metros, and what drives the gap."""
    if frame.empty:
        return "No metro reports enough of this occupation to rank."

    hardest = frame.iloc[0]
    easiest = frame.iloc[-1]

    # Which of the three signals actually separates them? Naming the driver is
    # the difference between "Seattle is hard" and "Seattle is hard because
    # supply is thin, not because wages are high".
    gaps = {
        "thin supply": hardest["scarcity_score"] - easiest["scarcity_score"],
        "wage premiums": hardest["wage_premium_score"] - easiest["wage_premium_score"],
        "a shrinking pool": hardest["growth_score"] - easiest["growth_score"],
    }
    driver = max(gaps, key=gaps.get)

    return (
        f"**{hardest['metro']}** is the toughest market for {occupation} "
        f"({hardest['competition_index']:.0f} / 100), and **{easiest['metro']}** "
        f"the easiest ({easiest['competition_index']:.0f}). The gap is driven "
        f"mostly by {driver}."
    )


def pool_summary(row: pd.Series) -> str:
    """One metro, in national context."""
    premium = row["wage_premium"]
    direction = "above" if premium >= 0 else "below"

    parts = [
        f"**{row['metro']}** holds **{row['employment']:,.0f}** {row['occupation']}, "
        f"the {_ordinal(int(row['rank_by_size']))} largest pool of "
        f"{int(row['metros_total'])} metros — "
        f"{row['share_of_national_pool']:.1%} of the national total.",
        f"Median pay is **${row['wage_p50']:,.0f}**, "
        f"{abs(premium):.0%} {direction} the national median for the role.",
    ]

    concentration = row["concentration_ratio"]
    if concentration >= 1.25:
        parts.append(
            f"The occupation is **{concentration:.1f}x more concentrated** here "
            "than in the average metro, so this is a specialist market."
        )
    elif concentration <= 0.75:
        parts.append(
            f"The occupation is **under-represented** here "
            f"({concentration:.1f}x the average metro's concentration)."
        )

    if bool(row["growth_unavailable"]):
        parts.append(
            "_Three-year supply growth is unavailable for this metro — BLS "
            "suppressed the prior-year estimate._"
        )
    else:
        growth = row["supply_growth_3y"]
        verb = "grew" if growth >= 0 else "shrank"
        parts.append(f"The local pool **{verb} {abs(growth):.0%}** over three years.")

    return " ".join(parts)


# ═════════════════════════════════════════════════════════════════════════════
#  Cost of Talent
# ═════════════════════════════════════════════════════════════════════════════


def arbitrage_summary(frame: pd.DataFrame, headcount: int, baseline_metro: str) -> str:
    """The headline saving — and immediately, whether it is real.

    Deliberately does not stop at the cheapest metro. The cheapest is very
    often too thin to hire from, and a recommendation that ignores that is
    worse than no recommendation. So the sentence names the best *viable*
    option too, whenever they differ.
    """
    if frame.empty:
        return "No metro reports enough of this occupation to compare."

    cheapest = frame.iloc[0]
    if cheapest["annual_delta_total"] >= 0:
        return (
            f"No metro is cheaper than **{baseline_metro}** for "
            f"{headcount} {_plural(headcount, 'hire')} at this wage percentile."
        )

    saving = abs(cheapest["annual_delta_total"])
    lead = (
        f"Hiring {headcount} in **{cheapest['metro']}** instead of "
        f"**{baseline_metro}** saves **{_money(saving)} a year** "
        f"({abs(cheapest['wage_delta_pct']):.0%} per hire)."
    )

    viable = frame[(frame["pool_depth"] != "Thin") & (frame["annual_delta_total"] < 0)]
    if viable.empty:
        return (
            f"{lead} But **every** metro cheaper than {baseline_metro} has a "
            f"pool too thin to absorb {headcount} hires in a year. Treat the "
            "saving as theoretical."
        )

    best_viable = viable.iloc[0]
    if best_viable["area_code"] == cheapest["area_code"]:
        return (
            f"{lead} The local pool of {cheapest['employment']:,.0f} can support "
            f"that comfortably ({cheapest['pool_depth'].lower()})."
        )

    return (
        f"{lead} But that pool is **thin** — only "
        f"{cheapest['hires_supportable']:,.0f} realistic "
        f"{_plural(cheapest['hires_supportable'], 'hire')} a year. The best "
        f"metro with depth to absorb {headcount} is **{best_viable['metro']}**, "
        f"still saving {_money(abs(best_viable['annual_delta_total']))}."
    )


# ═════════════════════════════════════════════════════════════════════════════
#  Skills & Sourcing
# ═════════════════════════════════════════════════════════════════════════════


def skill_summary(frame: pd.DataFrame, occupation: str) -> str:
    """What actually separates this role from the average professional job."""
    if frame.empty:
        return "No skill profile available for this occupation."

    distinctive = frame.sort_values("distinctive", ascending=False).head(3)
    names = [f"**{s}**" for s in distinctive["skill"]]
    joined = ", ".join(names[:-1]) + f" and {names[-1]}" if len(names) > 1 else names[0]

    top_raw = frame.sort_values("importance", ascending=False).iloc[0]

    return (
        f"{occupation} lean hardest on {joined} relative to the typical "
        f"occupation. By raw score the top skill is *{top_raw['skill']}* "
        f"({top_raw['importance']:.1f} / 5) — but nearly every white-collar "
        "role scores high there, which is why the chart centres on the "
        "cross-occupation average instead."
    )


def adjacency_summary(frame: pd.DataFrame, occupation: str) -> str:
    """Where else you could source from."""
    if frame.empty:
        return "No adjacent occupations found."

    nearest = frame.iloc[0]
    strengths = nearest.get("shared_strengths") or ""
    shared = [s.strip() for s in str(strengths).split(",") if s.strip()][:3]

    sentence = (
        f"The closest sourcing pool to {occupation} is "
        f"**{nearest['occupation']}** (similarity {nearest['similarity']:.2f})"
    )
    if shared:
        sentence += f", sharing unusual strength in {', '.join(shared)}"
    sentence += "."

    strong = frame[frame["similarity"] >= 0.4]
    if len(strong) > 1:
        sentence += (
            f" {len(strong)} occupations score above 0.40, so there is a real "
            "adjacent bench to recruit or reskill from."
        )
    elif nearest["similarity"] < 0.4:
        sentence += (
            " No occupation scores above 0.40 — this is a specialised profile "
            "with few natural substitutes."
        )

    return sentence


# ═════════════════════════════════════════════════════════════════════════════
#  Program Health
# ═════════════════════════════════════════════════════════════════════════════


def usage_summary(by_view: pd.DataFrame, total: int, days: int) -> str:
    """Whether anyone is actually using this."""
    if total == 0 or by_view.empty:
        return (
            "No usage recorded yet. Every view logs a row, so this fills in as "
            "the app gets used — which is the point: an insights programme that "
            "cannot answer *is anyone using this* has no way to earn its next "
            "quarter of investment."
        )

    top = by_view.iloc[0]
    share = top["events"] / total

    sentence = (
        f"**{total:,}** {_plural(total, 'view')} over {days} "
        f"{_plural(days, 'day')}. **{top['view_name']}** is the most used "
        f"({share:.0%} of all views)."
    )

    if len(by_view) > 1 and share > 0.6:
        sentence += (
            " That concentration is worth watching — either the other views are "
            "not landing, or they solve a problem people do not have."
        )
    return sentence


# ── Rendering ────────────────────────────────────────────────────────────────

_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", re.DOTALL)
_UNDERSCORE_ITALIC = re.compile(r"(?<!\w)_(.+?)_(?!\w)", re.DOTALL)
_CODE = re.compile(r"`(.+?)`", re.DOTALL)


def to_html(text: str) -> str:
    """Convert the light markdown these functions emit into HTML.

    The takeaway boxes are styled containers, which means Streamlit renders
    them with `unsafe_allow_html=True` — and inside a raw HTML block Streamlit
    does no markdown processing at all. Without this, every `**metro name**`
    reaches the screen as literal asterisks.

    Escapes first, then re-introduces only the four inline tags we emit, so a
    metro or occupation name containing `&` or `<` cannot inject markup.
    """
    out = html.escape(text, quote=False)
    out = _CODE.sub(r"<code>\1</code>", out)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    out = _UNDERSCORE_ITALIC.sub(r"<em>\1</em>", out)
    out = _ITALIC.sub(r"<em>\1</em>", out)
    return out
