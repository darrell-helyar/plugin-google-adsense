# google-adsense

Brings your Google AdSense earnings into NousViz. Each night it pulls the last 30 days of the AdSense daily report (estimated earnings, page views, impressions, clicks, CTR, page RPM) via the **AdSense Management API v2** and renders KPI tiles plus an earnings-over-time line chart — so you don't have to log into the AdSense console.

---

## What this plugin does

For anyone running AdSense who wants their revenue visible alongside their other NousViz dashboards. It authenticates to Google with an OAuth2 refresh token, fetches one row per day into Postgres (`goog_daily`), and surfaces:

- **KPIs:** 30-day earnings, 30-day clicks, average page RPM, last-sync age.
- **Trend:** estimated earnings per day over the last 30 days.

Read-only — it never writes back to AdSense.

---

## Setup

### 1. Get your four AdSense credentials

You need a **Client ID**, **Client secret**, **Refresh token**, and **Account ID**.

**Enable the API**
1. [Google Cloud Console](https://console.cloud.google.com) → create or pick a project.
2. **APIs & Services → Library** → search **"AdSense Management API"** → **Enable**.

**Create the OAuth client**
3. **APIs & Services → OAuth consent screen** → set up (External is fine) and add the scope `https://www.googleapis.com/auth/adsense.readonly`. Add your Google account as a **Test user**.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID** → Application type **Web application**.
5. Under **Authorized redirect URIs**, add exactly: `https://developers.google.com/oauthplayground`
6. Create → copy the **Client ID** and **Client secret**.

**Generate the refresh token** (one-time)
7. Open the [OAuth 2.0 Playground](https://developers.google.com/oauthplayground).
8. ⚙️ (top right) → tick **"Use your own OAuth credentials"** → paste your Client ID + secret.
9. In the left scope box, type `https://www.googleapis.com/auth/adsense.readonly` → **Authorize APIs** → sign in + consent.
10. Click **Exchange authorization code for tokens** → copy the **Refresh token**.

**Find your Account ID**
11. [AdSense console](https://adsense.google.com) → **Account → Settings → Account information** → your **Publisher ID** (`pub-XXXXXXXXXXXXXXXX`).

### 2. Install on NousViz

This plugin is `visibility: fully_private`, so install by **direct URL** (not the public marketplace). Full walkthrough: [docs/12-installing-on-nousviz.md](https://github.com/JoeHatch/nousviz-plugin-authoring/blob/main/docs/12-installing-on-nousviz.md).

1. NousViz → **Plugins → Install from URL** → paste `https://github.com/darrell-helyar/plugin-google-adsense` (NousViz resolves the latest tag, `v0.1.0`).
2. When the consent banner appears, click **Trust this plugin**, then **hard-refresh** once.

### 3. Configure → test → sync

3. Open the plugin → **Settings** tab → enter Client ID, Client secret, Refresh token, Account ID → **Save**.
4. Click **Test connection** → expect **"Connection OK — AdSense credentials authenticated."** (runs the live OAuth exchange).
5. Click **Run sync** → wait ~30s → the **Overview** KPIs and line chart populate.

### 4. Verify deployed = tagged (don't skip)

6. Hit `GET /api/plugins/google-adsense/health-check` and confirm `"version": "0.1.0"` with a non-null `latest_report_date`. Pushed-and-tagged ≠ installed-and-running.

The setup checklist on the plugin page guides you through steps 3–5.

---

## Modules / Tabs

- **Overview** — four KPI tiles (30-day earnings, 30-day clicks, average page RPM, last-sync age) and an estimated-earnings-per-day line chart.

---

## Data

- Imports into `goog_daily` — one row per calendar day — on a nightly cron (`0 3 * * *`), plus a manual **Run sync** button.
- Upserts on `report_date`, so re-running is idempotent: recent days are corrected as AdSense finalizes their estimates.
- Schema in `storage/migrations/`.

---

## Operator runbook

### Deploy key (one per plugin)

> **This repo is public**, so NousViz clones it over HTTPS and **no deploy key is needed**. The note below applies only if you later make the repo private.

NousViz core v0.9.5.9 (ticket B204) requires a per-repo deploy key. A single `github.com`-wide key no longer works — each plugin's repo needs its own entry registered against the exact `repo_url` (e.g. `git@github.com:<your-org>/plugin-example.git`).

Set this up via **Settings → Deploy Keys → Add deploy key** in the NousViz admin UI. Paste the private key, set the repo URL exactly, click the row's **Test** button to confirm. If you skip this step or use a key registered for a different repo, the install / update flow fails with `Permission denied (publickey)` and a `/system/logs` entry pointing you here.

Full walkthrough: see `docs/12-installing-on-nousviz.md` Step 1 in the [nousviz-plugin-authoring](https://github.com/JoeHatch/nousviz-plugin-authoring) guide.

### When something goes wrong

| Symptom | Where to look |
|---|---|
| Setup checklist stuck at N/4 | Each item maps to a predicate — see `plugin.yaml`'s `setup_checklist` block. Cross-reference `docs/appendix-gotchas.md G-6` in the parent guide. |
| Plugin install fails | `/system/logs?source=plugin_install` (since core v0.9.5.9 / B203). Look for `[google-adsense]` prefix on log lines. |
| Plugin update / "Check for updates" fails | `/system/logs?source=plugin_update`. Common cause: missing per-repo deploy key (B204 — see above). |
| Sync fails | `/system/logs?source=sync&plugin_id=google-adsense` |
| Action button shows error toast | Read the toast text — it includes the exception class. Full traceback at `/system/logs?source=plugin_route` |
| Hook (install / on_install / on_uninstall) failed | `/system/logs?source=plugin_install` or `?source=plugin_uninstall` (since core v0.9.5.9 / B203). |
| Custom widget shows placeholder card | Trust the plugin or hard-refresh. If still broken, browser console has the error |

---

## Development

```bash
# One-time setup (only if you ship a custom widget)
cd widget && npm install

# Make changes, then rebuild widget
cd widget && ./build.sh

# Quick "did the code work?" check (no NousViz core checkout needed)
/path/to/nousviz-plugin-authoring/scripts/smoke-test.sh

# Pre-tag release-readiness (security audit + bundle hygiene)
/path/to/nousviz-plugin-authoring/scripts/preflight.sh

# Commit + tag + push
git add -A && git commit -m "feat: ..."
git tag -a v0.1.1 -m "v0.1.1 — ..."
git push origin main && git push origin v0.1.1
```

The version in `plugin.yaml` and the git tag must match.

You don't need a local NousViz core checkout to develop this plugin — the install-time validator on your NousViz instance catches manifest and import errors. See `docs/01-getting-started.md` "Two paths to choose between" in the parent guide for the rare cases where a checkout helps.

---

## Updating

Operators update by clicking **Update** on the plugin's Settings page. NousViz pulls the latest `v*` tag and runs migrations. If `frontend.components` changed, the operator must re-trust the plugin.

Update notes go in `CHANGELOG.md` per release. The first line under each version's heading is what operators see.
