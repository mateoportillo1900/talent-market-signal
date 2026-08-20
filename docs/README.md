# Documentation

The written half of *Talent Market Signal*. The [top-level README](../README.md)
covers what the tool does; these cover why it is built the way it is, whether the
numbers can be trusted, and what would have to happen for anyone to use it.

Pick by what you came to check.

### "What was built, and for whom?"

| Document | What it covers |
|---|---|
| [**PRD.md**](./PRD.md) | The problem, the user who is *not* an analyst, jobs-to-be-done by customer lifecycle stage, the six requirements that shaped the build, and explicit non-goals. **Start here.** |

### "Can I trust the numbers?"

| Document | What it covers |
|---|---|
| [**METHODOLOGY.md**](./METHODOLOGY.md) | Every formula — Competition Index, wage arbitrage, skill adjacency — with each judgment call named as one. Ends with what the data cannot support |
| [**DATA_QUALITY.md**](./DATA_QUALITY.md) | Fatal / warn / note severity tiers, the three layers each check runs at, the tests that catch *silent* wrongness, and incident response |

### "Would anyone actually use it?"

| Document | What it covers |
|---|---|
| [**GTM_ENABLEMENT.md**](./GTM_ENABLEMENT.md) | Four-week pilot, cohort composition, gate criteria that can fail, the 45-minute enablement session, and the one-page cheat sheet |
| [**MEASUREMENT.md**](./MEASUREMENT.md) | Three tiers of confidence, the adoption funnel, and an honest account of why win-rate lift is **not** cleanly attributable |
| [**STAKEHOLDER_MAP.md**](./STAKEHOLDER_MAP.md) | Who is involved, RACI, and the four conflicts worth planning for before they arrive |

### "How was it built?"

| Document | What it covers |
|---|---|
| [**AI_ASSISTED_DEVELOPMENT.md**](./AI_ASSISTED_DEVELOPMENT.md) | Built with an AI assistant. Five confident errors it produced, how each was caught, and the rule that came out of it |

---

## Diagrams

Every diagram in these documents is [Mermaid](https://mermaid.js.org/), so GitHub
renders it inline and a diff shows what changed in the *logic* rather than a
binary blob. Nothing here depends on an image file being regenerated.

To export them as PNGs — for a slide, a portfolio page, or a LinkedIn post,
none of which render Mermaid:

```bash
make diagrams          # writes docs/images/*.png
```

The script derives each filename from the heading the diagram sits under, so
adding a diagram does not mean editing a list somewhere else.

`docs/img/` is separate and holds dashboard screenshots, which are captured by
hand from a running app.

---

## Conventions

- **Every document names an owner and a last-updated date.** A programme document
  with neither is a document nobody is accountable for.
- **Judgment calls are labelled as judgment calls.** Index weights, the 2% pool
  ceiling, the choice of percentile rank. Presenting a judgment as a derived
  result invites a challenge that cannot be answered.
- **Figures trace to a command.** If a document states a number, something in the
  repo produced it — see [`AI_ASSISTED_DEVELOPMENT.md`](./AI_ASSISTED_DEVELOPMENT.md) for why that rule exists.
