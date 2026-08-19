-- ═══════════════════════════════════════════════════════════════════════════
-- Most requested occupation x metro combinations
-- ═══════════════════════════════════════════════════════════════════════════
--
-- What people actually come here to look up. This is the demand signal that
-- should drive the roadmap: if one occupation family is 60%% of lookups, that
-- is where depth is worth adding, and the rest of the catalogue is breadth
-- nobody asked for.
--
-- Parameters
--   %(days)s   size of the window
--   %(limit)s  rows to return
-- ═══════════════════════════════════════════════════════════════════════════

SELECT
    u.soc_code,
    COALESCE(t.occupation, u.soc_code)       AS occupation,
    COALESCE(t.occupation_group, 'Unknown')  AS occupation_group,
    COUNT(*)                                 AS events,
    COUNT(DISTINCT u.session_id)             AS sessions
FROM mart.usage_log u
LEFT JOIN LATERAL (
    -- One label row per occupation. The occupation name lives on every metro
    -- row in the fact table, so this picks any one of them rather than
    -- fanning the join out across 40 metros and multiplying the counts.
    SELECT occupation, occupation_group
    FROM mart.talent_market
    WHERE soc_code = u.soc_code
    LIMIT 1
) t ON TRUE
WHERE u.occurred_at >= CURRENT_DATE - (%(days)s::int - 1)
  AND u.soc_code IS NOT NULL
GROUP BY u.soc_code, t.occupation, t.occupation_group
ORDER BY events DESC
LIMIT %(limit)s
