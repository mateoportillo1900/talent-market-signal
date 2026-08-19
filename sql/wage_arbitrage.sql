-- ═══════════════════════════════════════════════════════════════════════════
-- Wage Arbitrage
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Question it answers
--   "We are opening 20 of these roles. We assumed our HQ metro. What would
--    each alternative metro cost instead, and is the talent actually there?"
--
-- This is the query behind the Cost of Talent tab and the dollar figure in the
-- Talent Pool Report. It is the single number a customer remembers.
--
-- Two guardrails are built in on purpose:
--
--   1. Savings are reported against a chosen wage percentile, not always the
--      median. Hiring at p75 is a different business decision than hiring at
--      p50, and a savings figure that quietly assumes median hires is the kind
--      of number that gets a deck walked back in front of a CFO.
--
--   2. Every row carries `hires_supportable` and `pool_depth_ratio`. A metro
--      that is 30%% cheaper but holds 40 people in the occupation is not a
--      viable site, and the query should say so rather than let a sort by
--      savings put it on top.
--
-- Parameters
--   %(soc_code)s         occupation to price
--   %(baseline_area)s    area_code of the customer's current/HQ metro
--   %(headcount)s        number of hires being planned
--   %(percentile)s       one of 'p10','p25','p50','p75','p90'
--   %(min_employment)s   floor below which BLS estimates are too noisy
--
-- Portability
--   ANSI SQL throughout, including the CASE-based percentile pick, which
--   exists because the wage percentiles are stored as columns rather than
--   rows. Runs unchanged on Trino, Spark SQL, Snowflake or BigQuery.
-- ═══════════════════════════════════════════════════════════════════════════

WITH scoped AS (
    SELECT
        soc_code,
        occupation,
        area_code,
        metro,
        state,
        employment,
        employment_per_1k,
        supply_growth_3y,
        wage_p10,
        wage_p25,
        wage_p50,
        wage_p75,
        wage_p90,
        -- Resolve the requested percentile to a single comparable wage.
        CASE %(percentile)s
            WHEN 'p10' THEN wage_p10
            WHEN 'p25' THEN wage_p25
            WHEN 'p50' THEN wage_p50
            WHEN 'p75' THEN wage_p75
            WHEN 'p90' THEN wage_p90
        END AS wage_at_percentile
    FROM mart.talent_market
    WHERE soc_code = %(soc_code)s
      AND employment >= %(min_employment)s
),

baseline AS (
    -- Exactly one row: the metro the customer is comparing against.
    SELECT
        metro              AS baseline_metro,
        wage_at_percentile AS baseline_wage,
        employment         AS baseline_employment
    FROM scoped
    WHERE area_code = %(baseline_area)s
)

SELECT
    s.soc_code,
    s.occupation,
    s.area_code,
    s.metro,
    s.state,
    b.baseline_metro,
    s.employment,
    s.employment_per_1k,
    s.supply_growth_3y,

    -- ── Price ────────────────────────────────────────────────────────────
    s.wage_at_percentile,
    b.baseline_wage,
    s.wage_at_percentile - b.baseline_wage AS wage_delta_per_hire,
    (s.wage_at_percentile - b.baseline_wage)
        / NULLIF(b.baseline_wage, 0)       AS wage_delta_pct,

    -- ── The headline number ──────────────────────────────────────────────
    -- Negative means cheaper than baseline. Reported as annual base wage
    -- only: no benefits load, no equity, no relocation. METHODOLOGY.md says
    -- so plainly, because a "savings" figure that quietly bundles assumptions
    -- is worse than no figure.
    %(headcount)s * (s.wage_at_percentile - b.baseline_wage)
        AS annual_delta_total,
    %(headcount)s * s.wage_at_percentile
        AS annual_cost_total,

    -- ── Feasibility ──────────────────────────────────────────────────────
    -- How many of these hires the local pool could absorb before the plan is
    -- implausible. 2%% of an occupation's metro employment in a single year is
    -- already an aggressive assumption for one employer.
    FLOOR(s.employment * 0.02)                    AS hires_supportable,
    (s.employment * 0.02) / NULLIF(%(headcount)s, 0) AS pool_depth_ratio,
    CASE
        WHEN (s.employment * 0.02) >= %(headcount)s * 3 THEN 'Deep'
        WHEN (s.employment * 0.02) >= %(headcount)s     THEN 'Adequate'
        ELSE 'Thin'
    END AS pool_depth,

    s.area_code = %(baseline_area)s AS is_baseline

FROM scoped s
CROSS JOIN baseline b
WHERE s.wage_at_percentile IS NOT NULL
ORDER BY annual_delta_total ASC
