# PLAN.md

The SOP for this plugin. Every change goes through these gates **before** code is written:

1. **Ticket** — what's broken / what's missing, with specific evidence
2. **Plan** — 3-5 lines of how
3. **Test plan** — what success looks like (operator-visible checks — see `docs/11-verification-spec.md` in the parent guide for the template)
4. **CHANGELOG stub** — draft the user-facing entry

If any gate is missing, you don't have permission to write code. Same applies to Claude Code — it refuses without these gates filled in.

For a brand-new plugin: walk through the eight intake questions in `docs/00-conversation-starter.md` (parent guide) before filling in the v0.1.0 ticket below. The intake answers BECOME the ticket + plan + test plan.

Reference: see `docs/08-sop-and-discipline.md` in the parent `nousviz-plugin-authoring` guide.

---

## Implementation phases

### v0.1.0 — Initial AdSense earnings dashboard

**Ticket.** Operators want their Google AdSense earnings visible inside NousViz
without logging into the AdSense console. There's no AdSense data source today.
First version pulls the daily AdSense report via the AdSense Management API v2
and surfaces it as KPI cards + an earnings-over-time line chart.

Intake answers (from `docs/00-conversation-starter.md`):
1. **Source** — Google AdSense Management API v2 (REST).
2. **Credentials** — OAuth2: `client_id`, `client_secret`, `refresh_token`,
   plus a non-secret `account_id` (`pub-XXXXXXXX`). `client_secret` +
   `refresh_token` are `secret: true` (field-secrecy rule, CLAUDE.md).
3. **One row** — one row per day: `report_date` (unique key), `estimated_earnings`,
   `page_views`, `impressions`, `clicks`, `ctr`, `rpm`, `currency`, `raw_data`.
4. **See** — four stat KPIs (30-day earnings, 30-day clicks, avg page RPM, last
   sync age) + an earnings-over-time line chart.
5. **Do** — view + manual "Run sync" button. No write/edit.
6. **Freshness** — nightly, cron `0 3 * * *`, plus the manual button.
7. **Audience** — any logged-in NousViz user (`_require_analyst`).
8. **Success** — see the test plan below.

**Plan.**
1. plugin.yaml: replace the demo connection with the OAuth2 + `account_id`
   fields; set `databases.tables` to `goog_daily` + `goog_sync_state`; set
   sync schedule to `0 3 * * *`; category `analytics`.
2. Migration: replace `goog_items` with `goog_daily` (one row per day, unique
   on `report_date`); keep `goog_sync_state`. Mirror in the down migration.
3. Sync: exchange `refresh_token` → access token at Google's token endpoint,
   call `reports:generate` for `LAST_30_DAYS` with dimension `DATE`, upsert
   one row per day on `report_date`.
4. Routes: `/health-check`, `/test-connection` (token probe), `/sync-now`,
   `/kpis` (the four aggregates), `/daily` (chart series). Every data route
   gets `Depends(_require_analyst)`.
5. Dashboard: four stat KPIs + one `line_chart` of earnings by day.
6. `scripts/smoke-test.sh` then `scripts/preflight.sh`; fix failures.
7. Tag v0.1.0, install on dev NousViz, verify deployed version == tag.

**Test plan.** Operator-visible checks (intake Q8):

#### Install + first launch
- [ ] Install completes without error toast
- [ ] Sidebar shows "Google Adsense"
- [ ] Page loads at `/plugin/google-adsense` without "Plugin failed to load"
- [ ] No browser console errors

#### Settings tab
- [ ] Setup checklist shows 4 items
- [ ] Connection form shows: Client ID, Client secret, Refresh token, Account ID
- [ ] Client secret + Refresh token render as ●●●●●●●●; Client ID + Account ID render as plain text

#### Configure → test → sync
- [ ] Save credentials → "Configure connection" ticks green
- [ ] "Test connection" → success toast (token exchange OK) → "Verify connection" ticks green
- [ ] "Run sync" → sync queues + completes → "Run the first sync" ticks green
- [ ] Within 30s of install, "Confirm automatic sync is scheduled" ticks green

#### Overview dashboard
- [ ] Four KPI tiles show numeric values, no NaN (30-day earnings, 30-day clicks, avg RPM, last sync)
- [ ] 30-day earnings figure matches the AdSense console within rounding
- [ ] Earnings line chart renders with at least 28 daily points
- [ ] Browser console clean across page load + tab switching

#### Pre-tag verification
- [ ] `git ls-remote --tags origin` shows `v0.1.0` (tag pushed, not just local)
- [ ] `plugin.yaml` `version:` matches the latest tag exactly
- [ ] `scripts/smoke-test.sh` passes
- [ ] `scripts/preflight.sh` passes

**CHANGELOG stub.** See `CHANGELOG.md` "[0.1.0]".

---

### v0.2.0 — Current balance KPI

**Ticket.** v0.1.0 confirmed working on 2026-06-23 (real data: $5.71 earnings /
34 clicks / 7.91 RPM over the last 30 days, full daily chart). Operator now wants
the **current AdSense balance** ("what Google owes me right now" — unpaid
earnings) on the Overview dashboard next to the existing KPIs. Balance is a single
*current* figure (no daily history), so it's a stat tile, not a chart — and needs
no React widget.

**Plan.**
1. **Sync** — after the report fetch, call `accounts.payments.list` (same
   `adsense.readonly` scope), find the current *unpaid* balance entry, parse its
   amount + currency, and upsert into the existing `goog_sync_state` table under
   key `balance` (`{amount, currency, as_of}`). Wrap in try/except so a
   payments-API hiccup logs a warning but never fails the earnings sync. Verify
   the exact v2 payments response shape against the live API (don't assume field
   names) — handle both "amount as 'N.NN CUR' string" and structured forms.
2. **Dashboard** — add a `stat` panel "Current balance" reading
   `(value->>'amount')::numeric` from `goog_sync_state` where `key='balance'`,
   `fallback_empty: true` so it's blank until first synced.
3. **Ship** — bump `plugin.yaml` version + `routes.py` PLUGIN_VERSION to 0.2.0;
   surface balance in `/health-check`. No migration (reuses `goog_sync_state`).
   smoke + preflight; tag `v0.2.0` and push the tag.

**Test plan.** Operator-visible:
- [ ] After Update + Run sync, Overview shows a "Current balance" tile with a number matching the AdSense console "Your balance" (within rounding)
- [ ] Existing earnings / clicks / RPM tiles + chart unchanged (no regression)
- [ ] If the payments API errors, the earnings sync still completes (balance tile stays blank, warning in logs) — sync does not fail
- [ ] `git ls-remote --tags origin` shows `v0.2.0`; `plugin.yaml` version matches
- [ ] `scripts/smoke-test.sh` + `scripts/preflight.sh` pass

**CHANGELOG stub.** See `CHANGELOG.md` "[Unreleased]".

---

### v0.2.1 — Fix: Overview dashboard dropped by zero-row balance query

**Ticket.** After updating to v0.2.0 the **Overview tab disappeared** (verified
2026-06-23: Installed list shows v0.2.0, no error; the tab was present in v0.1.0
and vanished). Cause: the `current_balance` stat panel queries
`SELECT … FROM goog_sync_state WHERE key='balance'`, which returns **zero rows**
until the first balance is stored. Every other (working) stat panel uses an
aggregate (`COALESCE(SUM(...))`) that always returns exactly one row. A zero-row
result breaks the dashboard's load, so NousViz drops the whole dashboard (no
visible error). Earnings/clicks/RPM data itself is fine.

**Plan.**
1. Rewrite the `current_balance` query as a scalar subquery wrapped in
   `COALESCE(…, 0)` so it **always returns exactly one row** (0 until a balance
   is synced) — matching the pattern of the other tiles.
2. Bump version to 0.2.1 (plugin.yaml + routes.py); smoke + preflight; tag.

**Test plan.**
- [ ] After Update + hard refresh, the **Overview tab reappears** with all tiles (earnings, clicks, RPM, current balance, chart)
- [ ] Current balance tile shows 0 before a balance sync, then the real figure after
- [ ] No regression on the earnings tiles/chart
- [ ] `scripts/smoke-test.sh` + `scripts/preflight.sh` pass; `v0.2.1` tag pushed; version matches

**Follow-up (after confirmed fixed).** File a NousViz core ticket: a single
zero-row / malformed stat panel silently drops the entire dashboard with no
operator-visible error — any plugin can hit this. Robustness gap worth fixing in
core (skip the bad panel, surface the error) rather than every plugin defending
against it. Verify the repro before filing.

**CHANGELOG stub.** See `CHANGELOG.md` "[0.2.1]".

---

### v0.2.2 — Fix: Overview reachable via sidebar (per-dashboard navigation)

**Ticket.** Overview still missing after the v0.2.1 update; operator asked to fix
without reinstall. Compared `navigation:` across installed sibling plugins
(`plugin-intercom`, `plugin-statsdrone-stripe`, `plugin-quickbooks-online`): all
declare **one nav entry per dashboard** using `href: /plugin/<slug>/<dashboard>`
(e.g. `href: /plugin/intercom/overview`), which renders a reliable sidebar entry.
This plugin used the skeleton's single-entry shortcut (`path: /plugin/google-adsense`),
relying on the page-tab mechanism — which is what didn't survive updates. Switch
to the proven per-dashboard `href` pattern.

**Plan.**
1. `navigation:` — replace the single `path:` entry with `label: Overview`,
   `href: /plugin/google-adsense/overview`, `icon: DollarSign`.
2. Bump version 0.2.2; smoke + preflight; tag + push.

**Test plan.**
- [ ] After Update + hard refresh, "Google AdSense" in the sidebar exposes an **Overview** entry that loads the dashboard with all tiles (earnings, clicks, RPM, balance, chart)
- [ ] If Overview is STILL missing after the update → confirms NousViz updates don't re-register navigation/dashboards; reinstall is then required (and the update-re-registration gap is a core ticket)
- [ ] `scripts/smoke-test.sh` + `scripts/preflight.sh` pass; `v0.2.2` tag pushed; version matches

**CHANGELOG stub.** See `CHANGELOG.md` "[0.2.2]".

---

### v0.3.0 — Period tabs (30/60/90d, this year, last year, all time) + backfill + balance fix

**Ticket.** Operator wants earnings/clicks/RPM over selectable periods. UI chosen
2026-06-23: **period tabs** (one declarative dashboard per period) rather than a
custom-widget dropdown — reuses the proven per-dashboard navigation (v0.2.2),
avoids the fragile widget/Trust/update path. Also: balance still shows 0 — the
v0.2.x unpaid-detection guess (no-`date` entries) was wrong for this account.

**Plan.**
1. **Backfill** — sync report fetch switched from `dateRange=LAST_30_DAYS` to a
   custom `startDate`/`endDate` (~3 years, `BACKFILL_DAYS`) so This/Last year +
   All time have data. Sync raises a clear error if the date params are rejected.
2. **Balance fix** — detect the unpaid entry by **name ending in "unpaid"**
   (primary), fall back to no-`date` entries; **log the raw payments response**
   (names + amounts) to `/system/logs` so a remaining mismatch is diagnosable.
3. **Dashboards** — 6 declarative dashboards: `overview`(30d), `-60d`, `-90d`,
   `-ytd`, `-lastyear`, `-all`. Daily earnings chart for 30/60/90; **monthly**
   chart for the year-scale tabs so they stay readable. Shared `current_balance`
   + `last_sync_age` tiles (always-one-row, per the v0.2.1 fix).
4. **Navigation/dashboards** — one `href` nav entry + one `dashboards` entry per
   period (proven pattern). Bump 0.3.0; smoke + preflight; tag.

**Test plan.**
- [ ] After Update + hard refresh, tabs read: 30 Days | 60 Days | 90 Days | This Year | Last Year | All Time | Settings
- [ ] Each tab's KPIs + chart reflect that window; year tabs render a monthly chart
- [ ] After Run sync, All Time shows months older than 30 days (backfill worked)
- [ ] Current balance shows the real unpaid figure; if still 0, the sync log shows the raw payments entries (names/amounts) to finish the fix
- [ ] `scripts/smoke-test.sh` + `scripts/preflight.sh` pass; `v0.3.0` tag pushed; version matches

**Known risk (untested live).** The custom date-range param format and the
payments response shape are best-effort (no local AdSense to test). Both fail
*loudly*: a bad report range → sync error toast; a bad balance shape → 0 + the
logged raw payments. Iterate from the log if needed.

**CHANGELOG stub.** See `CHANGELOG.md` "[0.3.0]".

---

<!--
Template for subsequent versions — copy-paste and fill in:

### vX.Y.Z — <one-line summary>

**Ticket.** What's broken / what's missing. Cite specific evidence (error
message, log entry, file:line). Why this needs fixing now vs later.

**Plan.**
1. First step.
2. Second step.

**Test plan.** Use the template from `docs/11-verification-spec.md`. The
full template covers install, settings, configure/test/sync, dashboards,
custom-widget interactions, update flow, and "what the operator should
NOT see." For a small change, include just the sections affected.

- [ ] `git ls-remote --tags origin` shows the new tag (not just local)
- [ ] `plugin.yaml` `version:` matches the tag
- [ ] `scripts/smoke-test.sh` passes
- [ ] `scripts/preflight.sh` passes
- [ ] Operator-visible check 1 (specific to this version's change)
- [ ] Operator-visible check 2
- [ ] No regression on X
- [ ] No browser console errors

**CHANGELOG stub.**
\```
### Fixed/Added/Changed — vX.Y.Z: <summary>
- Bullet 1
\```
-->