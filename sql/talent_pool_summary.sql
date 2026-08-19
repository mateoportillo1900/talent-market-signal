-- ═══════════════════════════════════════════════════════════════════════════
-- Talent Pool Summary  —  one occupation, one metro, in national context
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Question it answers
--   "Give me everything I need to say about this role in this city."
--
-- This is the query behind the downloadable Talent Pool Report. Every figure
-- on that one-pager comes from this single row, which matters more than it
-- sounds: an asset assembled from six separate queries drifts, and a customer
-- eventually notices that the headline and the footnote disagree.
--
-- Every metro-level figure is returned alongside its national counterpart,
-- because a number without a comparison is not an insight. "$164,000" says
-- nothing. "$164,000, which is 27%% above the national median for this role"
-- is a sentence an account exec can build a conversation on.
--
-- Parameters
--   %(soc_code)s   occupation
--   %(area_code)s  metro
-- ═══════════════════════════════════════════════════════════════════════════

WITH national AS (
    -- Employment-weighted national aggregates for this occupation. Weighted,
    -- not a plain average across metros: an unweighted mean would let Knoxville
    -- and New York vote equally on the national wage, which is wrong.
    SELECT
        SUM(employment)                                     AS national_employment,
        SUM(employment * wage_p50) / NULLIF(SUM(employment), 0)
                                                            AS national_wage_weighted,
        AVG(employment_per_1k)                              AS national_per_1k_avg,
        SUM(employment * supply_growth_3y)
            FILTER (WHERE supply_growth_3y IS NOT NULL)
          / NULLIF(SUM(employment) FILTER (WHERE supply_growth_3y IS NOT NULL), 0)
                                                            AS national_growth_weighted,
        COUNT(*)                                            AS metros_reporting
    FROM mart.talent_market
    WHERE soc_code = %(soc_code)s
),

metro_rank AS (
    -- Where this metro sits among all metros for this occupation, on the two
    -- dimensions a customer asks about first: how big is the pool, and how
    -- expensive is it.
    SELECT
        area_code,
        RANK() OVER (ORDER BY employment DESC)  AS rank_by_size,
        RANK() OVER (ORDER BY wage_p50 DESC)    AS rank_by_wage,
        COUNT(*) OVER ()                        AS metros_total,
        PERCENT_RANK() OVER (ORDER BY wage_p50 ASC) AS wage_percentile_nationally
    FROM mart.talent_market
    WHERE soc_code = %(soc_code)s
)

SELECT
    t.soc_code,
    t.occupation,
    t.occupation_group,
    t.area_code,
    t.metro,
    t.state,

    -- ── Supply ───────────────────────────────────────────────────────────
    t.employment,
    t.employment_per_1k,
    t.supply_growth_3y,
    t.supply_growth_3y IS NULL AS growth_unavailable,
    t.proj_growth_10y,
    n.national_employment,
    t.employment / NULLIF(n.national_employment, 0) AS share_of_national_pool,
    n.national_per_1k_avg,
    t.employment_per_1k / NULLIF(n.national_per_1k_avg, 0) AS concentration_ratio,
    n.national_growth_weighted,

    -- ── Price ────────────────────────────────────────────────────────────
    t.wage_p10,
    t.wage_p25,
    t.wage_p50,
    t.wage_p75,
    t.wage_p90,
    t.national_wage_p50,
    n.national_wage_weighted,
    (t.wage_p50 / NULLIF(t.national_wage_p50, 0)) - 1.0 AS wage_premium,
    (t.wage_p75 - t.wage_p25) / NULLIF(t.wage_p50, 0)   AS wage_dispersion,

    -- ── Position ─────────────────────────────────────────────────────────
    r.rank_by_size,
    r.rank_by_wage,
    r.metros_total,
    r.wage_percentile_nationally,
    n.metros_reporting

FROM mart.talent_market t
CROSS JOIN national n
JOIN metro_rank r ON t.area_code = r.area_code
WHERE t.soc_code = %(soc_code)s
  AND t.area_code = %(area_code)s
