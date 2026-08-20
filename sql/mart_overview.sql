-- ═══════════════════════════════════════════════════════════════════════════
-- Mart Overview  —  what is actually in the warehouse
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Question it answers
--   "I just opened this. How much data is behind it, and how complete is it?"
--
-- This is the query behind the Overview tab's figures. It exists so those
-- numbers are read from the warehouse rather than typed into the UI: a scope
-- described in hardcoded copy is a scope that silently stops being true the
-- first time the dataset is rebuilt. The fixture reports 40 metros and the
-- real BLS extract reports far more, and the same screen has to be honest
-- about both without anyone remembering to edit it.
--
-- Returns exactly one row. Every column is a count or a coverage share, so
-- the UI does no arithmetic on the result.
--
-- Takes no parameters.
--
-- Portability
--   ANSI SQL. `FILTER (WHERE ...)` is `CASE WHEN` on engines without it;
--   everything else is unchanged on Trino, Spark SQL or Snowflake.
-- ═══════════════════════════════════════════════════════════════════════════

WITH talent AS (
    SELECT
        COUNT(*)                          AS talent_rows,
        COUNT(DISTINCT soc_code)          AS occupations,
        COUNT(DISTINCT area_code)         AS metros,
        COUNT(DISTINCT state)             AS states,
        -- Coverage, not a quality score. Three-year growth is null wherever a
        -- metro has no prior-vintage counterpart, which happens legitimately
        -- when boundaries are redrawn between OES releases. Surfacing the
        -- share keeps that visible instead of letting a sparse column look
        -- as complete as the rest.
        COUNT(*) FILTER (WHERE supply_growth_3y IS NOT NULL)  AS rows_with_growth,
        MIN(wage_p50)                     AS wage_p50_min,
        MAX(wage_p50)                     AS wage_p50_max
    FROM mart.talent_market
),

skills AS (
    SELECT
        COUNT(*)                          AS skill_rows,
        COUNT(DISTINCT skill)             AS skills_tracked,
        COUNT(DISTINCT soc_code)          AS occupations_with_skills
    FROM mart.skills
)

SELECT
    t.talent_rows,
    t.occupations,
    t.metros,
    t.states,
    t.rows_with_growth,
    ROUND(100.0 * t.rows_with_growth / NULLIF(t.talent_rows, 0), 1)
                                          AS growth_coverage_pct,
    t.wage_p50_min,
    t.wage_p50_max,
    s.skill_rows,
    s.skills_tracked,
    s.occupations_with_skills
FROM talent t
CROSS JOIN skills s
