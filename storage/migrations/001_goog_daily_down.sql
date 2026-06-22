-- 001_goog_daily_down.sql
--
-- Down companion to 001_goog_daily.sql. Core's uninstall handler runs every
-- *_down.sql in this directory in REVERSE lexicographic order when an
-- operator selects "Uninstall with Remove data" — without this file, the
-- plugin's tables would leak across uninstalls. See:
--
--   apps/api/src/routes/plugins.py: _run_down_migrations()
--   docs/02-plugin-contract.md     "Migrations: up + down pairs"
--   docs/appendix-gotchas.md       G-32
--
-- Naming convention is load-bearing: this file MUST be named
-- <NNN>_<base>_down.sql where <NNN>_<base>.sql is the up migration. Core
-- strips `_down.sql` from the filename to match against
-- `schema_migrations.filename` and delete the row.
--
-- Drops here mirror the creates in the up file in reverse dependency
-- order: indexes before their tables, dependent tables before their
-- parents. Use DROP … IF EXISTS so re-running is idempotent.

-- Sync state table (no dependents).
DROP TABLE IF EXISTS goog_sync_state;

-- Index on goog_daily. Postgres would CASCADE this with `DROP TABLE`, but an
-- explicit DROP keeps the intent readable and survives partial-migration
-- recovery.
DROP INDEX IF EXISTS idx_goog_daily_report_date;

-- The daily report table itself.
DROP TABLE IF EXISTS goog_daily;
