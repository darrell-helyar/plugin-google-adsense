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