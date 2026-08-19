-- ═══════════════════════════════════════════════════════════════════════════
-- Usage by day
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Views per day over a window, with empty days filled in.
--
-- The generate_series left join is the whole point. Without it, a day nobody
-- opened the app simply has no row, and a line chart drawn from that data
-- connects Tuesday straight to Thursday — silently hiding the gap it exists
-- to reveal. A zero is a fact; a missing row is a lie by omission.
--
-- Parameters
--   %(days)s   size of the window
-- ═══════════════════════════════════════════════════════════════════════════

WITH calendar AS (
    SELECT generate_series(
        (CURRENT_DATE - (%(days)s::int - 1))::timestamptz,
        CURRENT_DATE::timestamptz,
        INTERVAL '1 day'
    )::date AS day
),

events AS (
    SELECT
        occurred_at::date AS day,
        COUNT(*)          AS events
    FROM mart.usage_log
    WHERE occurred_at >= CURRENT_DATE - (%(days)s::int - 1)
    GROUP BY occurred_at::date
)

SELECT
    c.day,
    COALESCE(e.events, 0) AS events
FROM calendar c
LEFT JOIN events e ON c.day = e.day
ORDER BY c.day
