# Measuring whether this worked

**Owner:** Mateo Portillo · **Last updated:** August 2026

The job description asks for someone who can *"measure the effectiveness of
insights-driven interventions across our customer lifecycle."* This document is
my answer, including the part where the honest answer is "you can't, cleanly."

---

## The uncomfortable part first

**You cannot cleanly attribute a won deal to an insight.**

The AEs who adopt a new tool first are the ones who were already going to have
better quarters. They are curious, they prepare, they experiment. If you compare
insight-using AEs against non-users and report the win-rate gap as the tool's
impact, you will produce a number that is large, flattering, and mostly
measuring who volunteers for things.

I would rather say that out loud in a review than have a director find it in the
appendix. An insights function that oversells its own attribution loses the
credibility it needs to be believed about anything else.

So the measurement plan below is built in **three tiers of confidence**, and
each number is reported at the tier it actually earns.

---

## Tier 1 — Adoption. Cleanly measurable.

Instrumented in `mart.usage_log` from the first commit, deliberately: adding
telemetry later means the first two quarters are permanently unmeasurable.

```sql
-- Every view logs one row
INSERT INTO mart.usage_log (view_name, soc_code, area_code, session_id)
```

The funnel, and what each step actually tells you:

| Step | Definition | What it means |
|---|---|---|
| **Aware** | Received enablement | Nothing yet. A launch email is not adoption |
| **Activated** | Opened the tool at least once | Minimum precondition. Inflated by curiosity |
| **Returned** | Second session, > 24h after the first | **The honest signal.** Curiosity gets one visit; usefulness gets the second |
| **Habitual** | Used in 3+ distinct weeks | Made it into someone's actual workflow |

**Return rate is the metric to defend.** Activation can be manufactured by a
well-timed Slack message. Return cannot.

Also tracked, because it drives the roadmap rather than the scorecard:

- **What gets asked for** — `usage_top_requests` ranks occupations by lookups.
  If one family is 60% of demand, that is where depth is worth adding and the
  rest of the catalogue is breadth nobody wanted.
- **Where people stop** — a view with high entry and no return is either
  confusing or answering a question nobody has.

---

## Tier 2 — Behaviour change. Measurable with effort.

Adoption tells you a tool is being opened. It does not tell you anything reached
a customer. The bridge is whether the insight shows up **in the field's own
artefacts**:

| Signal | Source | Why it is better than usage |
|---|---|---|
| Insight referenced in opportunity notes | CRM text search | The AE chose to write it down |
| Insight appears in a QBR deck | Deck template with a tagged slide | It survived preparation |
| Customer asks a follow-up question about it | CSM logs a flag | **The strongest available signal** — the customer engaged with the substance |

That last row is the one worth building for. A customer asking *"where did that
number come from?"* is evidence the insight landed, and it costs one checkbox
to capture.

These require the field to do something, which means they will be
under-reported. Treat the counts as a floor, never a rate.

---

## Tier 3 — Business outcomes. Not cleanly attributable.

Win rate, renewal rate, expansion revenue.

**These are worth watching and not worth claiming.** The honest framing in a
review:

> *"Opportunities where an insight was referenced closed at X% against Y% for
> matched opportunities. That gap includes a selection effect we have not
> removed, so treat it as a reason to keep investing, not as a measured
> return."*

### What would actually let us claim it

If the impact question becomes load-bearing — someone wants a number to justify
headcount — these are the options, in order of rigour:

1. **Staged rollout as a natural experiment.** Roll out by region or segment in
   waves and compare cohorts across the boundary. Costs nothing extra if the
   rollout was going to be staged anyway, which is a good reason to stage it.
2. **Matched-pair comparison.** Match opportunities on segment, deal size, tenure
   and stage before comparing. Reduces the selection effect. Does not remove it.
3. **Randomised access.** Cleanest, and realistically unsellable — deliberately
   withholding a tool from half the field is a hard conversation for a benefit
   nobody has proven yet.

**Recommendation: option 1.** It is the only one that is both rigorous and free,
and it requires deciding to stage the rollout *before* launch. That is a
programme-design decision, not an analysis decision, which is exactly why it
belongs in this document rather than in a retrospective.

---

## What gets reported, and to whom

| Audience | Cadence | Content |
|---|---|---|
| Sales leadership | Monthly | Return rate, top requests, one worked example of an insight in a deal |
| Product & PMM | Monthly | Which views are used, which are ignored, what people asked for that we cannot answer |
| Data Science | Quarterly | Method changes, data-quality incidents, open attribution questions |
| Programme review | Quarterly | All three tiers, each labelled with its confidence |

**The label is the point.** A tier-3 number presented without its caveat is
worse than not presenting it, because it will be repeated without the caveat.

---

## Guardrail metrics

Things that would mean this is doing harm:

| Guardrail | Threshold | Response |
|---|---|---|
| Corrections issued after publication | **Zero tolerance** | Halt, root-cause, add a test before resuming |
| Insight cited outside its stated limits | Any occurrence | Enablement gap, not a user error |
| Time-to-answer regression | > 5s p95 | The four-minute-window user abandons |
| Data staleness unflagged | Any occurrence | The About tab must always state the vintage |

The first one has no acceptable non-zero value. One wrong number in front of a
customer costs more trust than ten good insights earn, and the field will
correctly stop using a tool that has embarrassed them once.

---

## Why the Program Health tab is small

It reports adoption and nothing else, and the tab says so:

> *Adoption counts tell you a tool is being opened, not that a decision changed.*

Building an impressive-looking impact dashboard on top of tier-3 data would be
the single most misleading thing in this project. The tab shows what is honestly
measurable and points here for the rest.
