-- ═══════════════════════════════════════════════════════════════════════════
-- Usage by view
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Which parts of the product get opened, and by how many distinct sessions.
--
-- Both numbers matter and they answer different questions. Raw views tell you
-- what gets clicked; distinct sessions tell you how many people that
-- represents. A view with 400 events from 2 sessions is one person leaning on
-- the slider, not adoption.
--
-- Parameters
--   %(days)s   size of the window
-- ═══════════════════════════════════════════════════════════════════════════

SELECT
    view_name,
    COUNT(*)                    AS events,
    COUNT(DISTINCT session_id)  AS sessions,
    MAX(occurred_at)            AS last_seen
FROM mart.usage_log
WHERE occurred_at >= CURRENT_DATE - (%(days)s::int - 1)
GROUP BY view_name
ORDER BY events DESC
