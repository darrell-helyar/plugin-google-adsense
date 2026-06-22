-- 001_goog_daily.sql
--
-- One row per calendar day of the Google AdSense daily report. The sync
-- upserts on `report_date`, so re-running the sync over an overlapping date
-- range is idempotent (yesterday's estimate gets corrected as AdSense
-- finalizes it). The `goog_` prefix matches `databases.postgres.table_prefix`
-- in plugin.yaml.
--
-- Migration files run in lexicographic order at install time. Number them
-- 001_, 002_, … to keep ordering predictable. Each migration runs once per
-- install. Don't edit a migration that's already shipped — write a new one.
--
-- Every CREATE here MUST have a matching DROP IF EXISTS in the companion
-- 001_goog_daily_down.sql, which core runs in reverse-lex order on
-- "Uninstall with Remove data". See docs/02-plugin-contract.md
-- "Migrations: up + down pairs" and appendix-gotchas.md G-32.

CREATE TABLE IF NOT EXISTS goog_daily (
    id                  BIGSERIAL PRIMARY KEY,
    report_date         DATE NOT NULL UNIQUE,        -- upsert key (one row/day)
    estimated_earnings  NUMERIC(14, 2) DEFAULT 0,    -- in `currency`
    page_views          BIGINT DEFAULT 0,
    impressions         BIGINT DEFAULT 0,
    clicks              BIGINT DEFAULT 0,
    ctr                 NUMERIC(8, 5) DEFAULT 0,      -- clicks / impressions ratio
    rpm                 NUMERIC(14, 2) DEFAULT 0,     -- page RPM
    currency            TEXT DEFAULT 'USD',
    raw_data            JSONB DEFAULT '{}'::jsonb,    -- full report row, for debugging
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Charts and KPIs scan by date; index it.
CREATE INDEX IF NOT EXISTS idx_goog_daily_report_date ON goog_daily (report_date);

-- Sync state table — used by the sync to track checkpoints, last successful
-- run, etc. Two columns: a key + a JSON blob. Schema-less by design.

CREATE TABLE IF NOT EXISTS goog_sync_state (
    key         TEXT PRIMARY KEY,
    value       JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
