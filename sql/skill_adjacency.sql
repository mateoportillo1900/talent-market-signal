-- ═══════════════════════════════════════════════════════════════════════════
-- Skill Adjacency  —  mean-centered cosine similarity over O*NET vectors
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Question it answers
--   "We cannot find enough of this role. Which other occupations share enough
--    of its skill profile that we could realistically source or reskill from
--    them?"
--
-- This is the query that turns the app from a reporting tool into an insights
-- tool. Supply and wage data tells a customer their market is tight; adjacency
-- tells them what to do about it.
--
-- ── Why mean-centered, not raw cosine ──────────────────────────────────────
--
--   O*NET importance sits on a 1-5 scale and is strictly positive. Raw cosine
--   between any two occupations therefore lands around 0.93-0.99 — every pair
--   looks similar, and the ranking is dominated by which occupations happen to
--   score high on everything. Sorting that produces a confident, useless list.
--
--   Subtracting each skill's cross-occupation mean first removes that shared
--   baseline. What remains is how each occupation *deviates* from the typical
--   profile, and the similarity becomes a correlation over deviations. Two
--   occupations now rank as adjacent because they are unusual in the same
--   direction — both lean on Programming and Systems Analysis, both under-use
--   Negotiation — which is the thing a sourcing strategy actually rests on.
--
--   Measured effect, scoring all 62 occupations against Software Developers:
--
--                     range              spread
--     raw cosine      0.864  to  0.978    0.113
--     centered       -0.465  to  0.696    1.161   ~10x wider
--
--   Same ordering at the very top, but raw cosine packs 62 occupations into
--   eleven-hundredths of a point, so the gap between the 3rd and the 30th
--   best sourcing candidate is smaller than the noise in the underlying O*NET
--   ratings. Centered cosine also pushes genuinely unrelated work down where
--   it belongs: Registered Nurses falls from 41st to 56th of 62.
--
--   (Those figures are from the synthetic fixture, whose occupations are
--   generated from group templates and so separate more cleanly than real
--   O*NET data will. The compression problem with raw cosine is a property of
--   the measure, not of the fixture; the exact numbers will move.)
--
-- Parameters
--   %(soc_code)s   the occupation to find neighbours for
--   %(limit)s      how many neighbours to return
--
-- Portability
--   ANSI SQL throughout. `string_agg` is `listagg` on Trino and
--   `array_join(collect_list(...))` on Spark SQL; everything else is unchanged.
-- ═══════════════════════════════════════════════════════════════════════════

WITH skill_means AS (
    -- The typical importance of each skill across all occupations in scope.
    -- This is the baseline being removed.
    SELECT
        skill,
        AVG(importance) AS mean_importance
    FROM mart.skills
    GROUP BY skill
),

centered AS (
    -- Every occupation's vector, expressed as deviations from that baseline.
    SELECT
        s.soc_code,
        s.skill,
        s.importance,
        s.importance - m.mean_importance AS deviation
    FROM mart.skills s
    JOIN skill_means m ON s.skill = m.skill
),

norms AS (
    -- Vector magnitude, precomputed once per occupation rather than
    -- recomputed inside every pairwise comparison.
    SELECT
        soc_code,
        SQRT(SUM(deviation * deviation)) AS norm
    FROM centered
    GROUP BY soc_code
),

target AS (
    SELECT skill, importance, deviation
    FROM centered
    WHERE soc_code = %(soc_code)s
),

target_norm AS (
    SELECT norm FROM norms WHERE soc_code = %(soc_code)s
),

pairwise AS (
    -- One row per candidate occupation. The join on `skill` is what pairs the
    -- two vectors component-wise; the GROUP BY collapses each pair to a single
    -- dot product.
    SELECT
        c.soc_code,
        SUM(c.deviation * t.deviation) AS dot_product,
        -- Skills where BOTH occupations sit above the cross-occupation mean.
        -- These are the shared strengths worth naming in a recommendation:
        -- "both lean unusually hard on Programming and Systems Analysis."
        string_agg(
            CASE WHEN c.deviation > 0 AND t.deviation > 0 THEN c.skill END,
            ', '
            ORDER BY LEAST(c.deviation, t.deviation) DESC
        ) AS shared_strengths,
        COUNT(*) FILTER (WHERE c.deviation > 0 AND t.deviation > 0)
            AS shared_strength_count
    FROM centered c
    JOIN target t ON c.skill = t.skill
    WHERE c.soc_code <> %(soc_code)s
    GROUP BY c.soc_code
)

SELECT
    p.soc_code,
    p.dot_product,
    -- Centered cosine, in [-1, 1]. Negative means the two occupations deviate
    -- from the baseline in opposite directions — genuinely poor sourcing
    -- candidates, not merely weak ones.
    p.dot_product / NULLIF(n.norm * tn.norm, 0) AS similarity,
    p.shared_strength_count,
    p.shared_strengths
FROM pairwise p
JOIN norms n       ON p.soc_code = n.soc_code
CROSS JOIN target_norm tn
WHERE p.dot_product / NULLIF(n.norm * tn.norm, 0) IS NOT NULL
ORDER BY similarity DESC
LIMIT %(limit)s
