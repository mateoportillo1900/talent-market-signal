-- ═══════════════════════════════════════════════════════════════════════════
-- Skill Profile
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Question it answers
--   "What actually defines this role, and which of those skills are
--    distinctive rather than table stakes?"
--
-- Returns both numbers for every skill, because they answer different
-- questions and confusing them produces bland output:
--
--   importance   the raw O*NET 1-5 score. Sorting by this returns Active
--                Listening and Reading Comprehension for nearly every
--                white-collar occupation. True, and useless in a customer
--                conversation.
--
--   distinctive  the same score minus the cross-occupation mean for that
--                skill. Sorting by this returns Programming for developers
--                and Negotiation for sales — the skills that actually
--                separate the role from the average professional job.
--
-- The app charts `importance` (a radar of raw scores reads naturally) and
-- narrates `distinctive` (the recommendation text names the skills that set
-- the role apart).
--
-- Parameters
--   $soc_code   occupation to profile
-- ═══════════════════════════════════════════════════════════════════════════

WITH skill_means AS (
    SELECT
        skill,
        AVG(importance)    AS mean_importance,
        STDDEV(importance) AS sd_importance
    FROM skills
    GROUP BY skill
)

SELECT
    s.soc_code,
    s.skill,
    s.importance,
    m.mean_importance,
    s.importance - m.mean_importance AS distinctive,
    -- Standardized, so "1.8 standard deviations above typical" is available
    -- for phrasing. NULLIF guards a skill with zero variance across
    -- occupations, which would otherwise divide by zero.
    (s.importance - m.mean_importance) / NULLIF(m.sd_importance, 0) AS z_score,
    PERCENT_RANK() OVER (ORDER BY s.importance ASC) AS within_role_rank
FROM skills s
JOIN skill_means m ON s.skill = m.skill
WHERE s.soc_code = $soc_code
ORDER BY s.importance DESC
