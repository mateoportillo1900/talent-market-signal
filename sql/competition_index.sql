-- ═══════════════════════════════════════════════════════════════════════════
-- Talent Competition Index
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Question it answers
--   "We need to hire this role. Rank every metro by how hard that will be."
--
-- Method
--   Three signals, each converted to a 0-100 percentile rank across the metros
--   in scope, then combined on the weights in tms/schema.py:INDEX_WEIGHTS.
--
--     scarcity      supply is thin relative to the metro's total job base
--     wage_premium  the metro pays above the national median for this role
--     growth        the local pool is shrinking, or growing slowly
--
--   Percentile rank rather than z-score or min-max on purpose. BLS employment
--   is long-tailed — New York has ~40x the software developers of Knoxville —
--   so min-max would compress every mid-size metro into the bottom few points
--   and a z-score would be dragged by the same outliers. A rank is unbothered
--   by both, and "83rd percentile for scarcity" is a sentence an account exec
--   can say out loud to a customer.
--
-- Parameters
--   %(soc_code)s        occupation to score
--   %(min_employment)s  floor below which BLS estimates are too noisy to rank
--   %(w_scarcity)s, %(w_wage_premium)s, %(w_growth)s   weights, must sum to 1.0
--
-- Portability
--   ANSI window functions and CTEs only. Runs unchanged on Trino, Spark SQL,
--   Snowflake or BigQuery against the same logical tables; Postgres is just
--   what is convenient to host for free.
--
-- Performance
--   `scoped` narrows to one occupation first, and `talent_market_soc_idx`
--   covers that predicate. Verified plan (scripts/explain_queries.py):
--
--     Bitmap Heap Scan on talent_market  (rows=40)
--       Recheck Cond: (soc_code = '15-1252')
--       ->  Bitmap Index Scan on talent_market_soc_idx
--             Index Cond: (soc_code = '15-1252')
--
--   An index seek to 40 rows, not a scan of all 2,520. Every CTE downstream
--   inherits that narrowing, so the window functions sort 40 rows rather than
--   the whole table.
-- ═══════════════════════════════════════════════════════════════════════════

WITH scoped AS (
    -- Narrow once, up front. Every later CTE inherits this filter rather than
    -- re-scanning the base table.
    SELECT
        soc_code,
        occupation,
        occupation_group,
        area_code,
        metro,
        state,
        employment,
        employment_per_1k,
        supply_growth_3y,
        proj_growth_10y,
        wage_p10,
        wage_p25,
        wage_p50,
        wage_p75,
        wage_p90,
        national_wage_p50
    FROM mart.talent_market
    WHERE soc_code = %(soc_code)s
      AND employment >= %(min_employment)s
),

growth_fallback AS (
    -- BLS suppresses small cells, so some metros have no prior-vintage
    -- employment and therefore no 3-year growth. Dropping those metros would
    -- silently shrink the ranking; imputing a national-average growth would
    -- overstate confidence. We impute this occupation's median growth across
    -- the metros that DO report, and carry a flag so the UI can mark the cell.
    SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY supply_growth_3y) AS median_growth
    FROM scoped
    WHERE supply_growth_3y IS NOT NULL
),

signals AS (
    SELECT
        s.*,
        COALESCE(s.supply_growth_3y, g.median_growth) AS growth_filled,
        s.supply_growth_3y IS NULL                    AS growth_imputed,
        -- Wage premium as a fraction: 0.18 means this metro's median sits 18%%
        -- above the national median for the occupation. NULLIF guards the
        -- divide; a zero national median means a broken build, not a free role.
        (s.wage_p50 / NULLIF(s.national_wage_p50, 0)) - 1.0 AS wage_premium,
        -- Spread between the 25th and 75th percentile, relative to the median.
        -- A wide band means title inflation or seniority mixing inside one SOC
        -- code, which is a caveat worth surfacing rather than burying.
        (s.wage_p75 - s.wage_p25) / NULLIF(s.wage_p50, 0)   AS wage_dispersion
    FROM scoped s
    CROSS JOIN growth_fallback g
),

ranked AS (
    SELECT
        *,
        -- DESC: the metro with the MOST supply per 1,000 jobs ranks 0 (least
        -- scarce); the thinnest market ranks 100.
        100.0 * PERCENT_RANK() OVER (ORDER BY employment_per_1k DESC)
            AS scarcity_score,
        -- ASC: the metro paying the largest premium ranks 100.
        100.0 * PERCENT_RANK() OVER (ORDER BY wage_premium ASC)
            AS wage_premium_score,
        -- DESC: the fastest-growing pool ranks 0; a shrinking pool ranks 100,
        -- because supply leaving the market is what makes hiring hard.
        100.0 * PERCENT_RANK() OVER (ORDER BY growth_filled DESC)
            AS growth_score
    FROM signals
)

SELECT
    soc_code,
    occupation,
    occupation_group,
    area_code,
    metro,
    state,
    employment,
    employment_per_1k,
    supply_growth_3y,
    growth_imputed,
    proj_growth_10y,
    wage_p10,
    wage_p25,
    wage_p50,
    wage_p75,
    wage_p90,
    national_wage_p50,
    wage_premium,
    wage_dispersion,
    scarcity_score,
    wage_premium_score,
    growth_score,
    -- The composite. Bounded to [0, 100] by construction: each component is a
    -- percentile rank in [0, 100] and the weights sum to 1.
    ( %(w_scarcity)s     * scarcity_score
    + %(w_wage_premium)s * wage_premium_score
    + %(w_growth)s       * growth_score
    ) AS competition_index,
    RANK() OVER (
        ORDER BY ( %(w_scarcity)s     * scarcity_score
                 + %(w_wage_premium)s * wage_premium_score
                 + %(w_growth)s       * growth_score ) DESC
    ) AS difficulty_rank
FROM ranked
ORDER BY competition_index DESC
