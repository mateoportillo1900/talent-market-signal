"""
Tests for the Program Health queries.

These run against whatever the usage log happens to contain, so they assert
structure and invariants rather than specific counts.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tms import db, metrics


@pytest.fixture(scope="module")
def usage():
    return metrics.usage_summary(days=30)


def test_usage_returns_every_section(usage) -> None:
    assert set(usage) == {
        "by_day",
        "by_view",
        "top_requests",
        "sessions",
        "occupations",
    }


def test_by_day_fills_empty_days(usage) -> None:
    """A day with no activity must appear as a zero, not go missing.

    A line chart built from gappy data draws Tuesday straight to Thursday and
    hides exactly the quiet stretch the chart exists to show.
    """
    by_day = usage["by_day"]
    assert len(by_day) == 30, f"expected 30 rows for a 30-day window, got {len(by_day)}"
    assert by_day["events"].notna().all()
    days = pd.to_datetime(by_day["day"])
    assert (days.diff().dropna() == pd.Timedelta(days=1)).all(), "gap in the calendar"


def test_by_day_is_chronological(usage) -> None:
    assert pd.to_datetime(usage["by_day"]["day"]).is_monotonic_increasing


def test_by_view_is_sorted_and_sessions_never_exceed_events(usage) -> None:
    by_view = usage["by_view"]
    if by_view.empty:
        pytest.skip("no usage logged yet")
    assert by_view["events"].is_monotonic_decreasing
    assert (by_view["sessions"] <= by_view["events"]).all(), (
        "distinct sessions cannot exceed total events"
    )


def test_top_requests_do_not_fan_out_across_metros() -> None:
    """The LATERAL join must pick one label row, not multiply by 40 metros.

    Joining usage to the fact table on soc_code alone would inflate every
    count by the number of metros reporting that occupation — a bug that
    produces plausible, badly wrong numbers.
    """
    db.execute(
        """
        INSERT INTO mart.usage_log (view_name, soc_code, area_code, session_id)
        VALUES ('__test__', '15-1252', '41860', '__test_session__')
        """
    )
    try:
        out = metrics.usage_summary(days=1, top_n=50)
        requests = out["top_requests"]
        row = requests[requests["occupation"] == "Software Developers"]
        assert not row.empty
        logged = db.run_query(
            """
            SELECT COUNT(*) AS n FROM mart.usage_log
            WHERE soc_code = '15-1252'
              AND occurred_at >= CURRENT_DATE
            """
        ).iloc[0]["n"]
        assert int(row.iloc[0]["events"]) == int(logged), (
            "event count was multiplied by the join"
        )
    finally:
        db.execute("DELETE FROM mart.usage_log WHERE session_id = '__test_session__'")


def test_usage_rejects_a_zero_window() -> None:
    with pytest.raises(ValueError, match="days must be at least 1"):
        metrics.usage_summary(days=0)


# ── Connection handling ──────────────────────────────────────────────────────


def test_queries_reuse_pooled_connections() -> None:
    """Repeated queries must not open a connection each.

    Against a local socket, connection-per-query is invisible. Against a
    hosted Postgres it is a TLS handshake per query over the internet, and
    a free tier's concurrent-connection cap is reachable faster than it
    looks — Streamlit re-runs the whole script on every widget interaction.
    """
    from tms import metrics

    for _ in range(20):
        metrics.competition_index("15-1252")

    backends = db.run_query(
        """
        SELECT COUNT(*) AS n
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND backend_type = 'client backend'
        """
    ).iloc[0]["n"]

    assert int(backends) <= db.POOL_MAX + 1, (
        f"{backends} backends open after 20 queries — the pool is not being "
        f"reused (max is {db.POOL_MAX})"
    )


def test_pool_is_a_singleton() -> None:
    """One pool per process. A second would double the connection count."""
    assert db.pool() is db.pool()
