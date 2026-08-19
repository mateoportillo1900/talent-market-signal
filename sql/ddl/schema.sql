-- ═══════════════════════════════════════════════════════════════════════════
-- Warehouse DDL
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Two tables in one schema. The app reads only from `mart` and never from a
-- staging or load table, so the schema name is the contract boundary: anything
-- in here is stable and queryable, anything outside it is build machinery.
--
-- Run by scripts/load_to_postgres.py before every load. Idempotent.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE SCHEMA IF NOT EXISTS mart;


-- ── Occupation x metro facts ───────────────────────────────────────────────
DROP TABLE IF EXISTS mart.talent_market CASCADE;

CREATE TABLE mart.talent_market (
    -- Keys
    soc_code            text        NOT NULL,
    occupation          text        NOT NULL,
    occupation_group    text        NOT NULL,
    area_code           text        NOT NULL,
    metro               text        NOT NULL,
    state               text        NOT NULL,

    -- Supply
    employment          double precision NOT NULL,
    employment_per_1k   double precision,
    employment_prior    double precision,
    supply_growth_3y    double precision,
    proj_growth_10y     double precision,

    -- Price, annual USD
    wage_p10            double precision,
    wage_p25            double precision,
    wage_p50            double precision NOT NULL,
    wage_p75            double precision,
    wage_p90            double precision,
    national_wage_p50   double precision,

    PRIMARY KEY (soc_code, area_code),

    -- Constraints the loader cannot skip. A percentile inversion or a negative
    -- wage is a parse bug, and it is far cheaper to reject the load than to
    -- discover it later in a chart someone already showed a customer.
    CONSTRAINT wage_percentiles_ordered CHECK (
        (wage_p10 IS NULL OR wage_p25 IS NULL OR wage_p10 <= wage_p25) AND
        (wage_p25 IS NULL OR wage_p25 <= wage_p50) AND
        (wage_p75 IS NULL OR wage_p50 <= wage_p75) AND
        (wage_p75 IS NULL OR wage_p90 IS NULL OR wage_p75 <= wage_p90)
    ),
    CONSTRAINT wages_positive CHECK (wage_p50 > 0),
    CONSTRAINT employment_positive CHECK (employment > 0)
);

-- Every analytical query filters on soc_code first and most of them rank
-- metros within it, so this is the index that matters. The included columns
-- let the planner answer the common "supply and price for one occupation"
-- shape from the index alone.
CREATE INDEX talent_market_soc_idx
    ON mart.talent_market (soc_code)
    INCLUDE (employment, employment_per_1k, wage_p50, national_wage_p50);

CREATE INDEX talent_market_area_idx ON mart.talent_market (area_code);


-- ── Occupation x skill vectors ─────────────────────────────────────────────
DROP TABLE IF EXISTS mart.skills CASCADE;

CREATE TABLE mart.skills (
    soc_code    text             NOT NULL,
    skill       text             NOT NULL,
    importance  double precision NOT NULL,

    PRIMARY KEY (soc_code, skill),

    -- O*NET's Importance scale. A value outside it means the wrong scale got
    -- parsed out of the source file, which would silently distort every
    -- similarity score computed from these vectors.
    CONSTRAINT importance_on_onet_scale CHECK (importance BETWEEN 1.0 AND 5.0)
);

-- Adjacency joins occupation vectors on `skill`, so this is the driving index.
CREATE INDEX skills_skill_idx ON mart.skills (skill) INCLUDE (importance);


-- ── Usage log ──────────────────────────────────────────────────────────────
-- Powers the Program Health view: which insights actually get pulled, by whom,
-- and when. An insights program that cannot answer "is anyone using this"
-- has no way to earn its next quarter of investment.
CREATE TABLE IF NOT EXISTS mart.usage_log (
    event_id     bigserial PRIMARY KEY,
    occurred_at  timestamptz NOT NULL DEFAULT now(),
    view_name    text        NOT NULL,
    soc_code     text,
    area_code    text,
    session_id   text,
    detail       jsonb
);

CREATE INDEX IF NOT EXISTS usage_log_occurred_idx ON mart.usage_log (occurred_at DESC);
CREATE INDEX IF NOT EXISTS usage_log_view_idx ON mart.usage_log (view_name);
