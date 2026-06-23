# Changelog

All notable changes to this plugin are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned later (v0.3.0)

- Selectable date ranges (Last 7 / 30 / 90 / 365 days, This year, All time), 3 years of history, and a payments-received list — these need an interactive React widget.

---

## [0.2.1] — Fix: Overview dashboard disappeared

### Fixed

- The Overview tab vanished after updating to 0.2.0. The new "Current balance" tile used a query that returns zero rows until a balance is stored, which broke the whole dashboard's load. The tile now always returns a single value (0 until first synced), so Overview renders normally.

---

## [0.2.0] — Current balance KPI

### Added

- **Current balance.** A "Current balance (unpaid)" KPI tile on the Overview dashboard showing your current unpaid AdSense earnings (what Google owes you right now), fetched from the AdSense payments endpoint. Best-effort: a payments-API error never blocks the earnings sync.

---

## [0.1.0] — Initial release

### Added

- Google AdSense earnings dashboard. Pulls the daily AdSense report (last 30 days) from the AdSense Management API v2 and surfaces it inside NousViz.
- OAuth2 connection: Client ID, Client secret, Refresh token, and Account ID (`pub-XXXXXXXX`). Client secret and refresh token are stored encrypted; Client ID and Account ID are plain config.
- Overview dashboard: four KPI tiles (30-day earnings, 30-day clicks, average page RPM, last sync age) and an earnings-over-time line chart.
- Nightly sync at 03:00 (cron `0 3 * * *`) plus a manual **Run sync** button. **Test connection** verifies the OAuth token exchange.
- One Postgres migration creating `goog_daily` (one row per day, keyed on `report_date`) and `goog_sync_state`.

### Plugin author release checklist (every release)

1. Bump `version:` in `plugin.yaml` to match this CHANGELOG entry's heading.
2. Commit code: `git commit -m "feat/fix: ..."`.
3. Push code: `git push origin main`.
4. **Tag the release**: `git tag -a v0.1.0 -m "v0.1.0 — ..."`.
5. **Push the tag**: `git push origin v0.1.0`. (`git push` alone doesn't push tags.)
6. Only then tell operators to install / Update.

NousViz pulls the latest semver tag — without step 4+5, install fails with `Plugin not found at tag vX.Y.Z`.

### Operator workflow on first install

- Install plugin → click **Trust this plugin** when the consent banner appears → hard-refresh the page once.
- Configure credentials on the Settings tab → click **Test connection** → click **Run sync**.
- Setup checklist guides you through the four steps; once all four are checked, the plugin is fully operational.
