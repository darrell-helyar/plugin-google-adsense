"""
src/google_adsense_sync.py — Sync script for google-adsense.

Subclasses BaseSyncScript so every invocation gets a job_runs row,
heartbeat support, and cancel-check support automatically.

One run = pull the last 30 days of the Google AdSense daily report
(AdSense Management API v2) and upsert one row per day into goog_daily.
Upserting on report_date makes re-runs idempotent — AdSense keeps
refining recent days' estimated earnings, so the latest sync wins.

The filename is slug-prefixed (`google_adsense_sync.py`, not bare
`sync.py`) so it can't collide with a sibling plugin's `sync.py`
via Python's sys.modules cache. See appendix-gotchas.md G-1.

Reference: docs/06-sync-and-jobs.md
"""

from __future__ import annotations

from typing import Any

# requests is a stdlib-adjacent dependency (the SDK does NOT wrap external
# HTTP — see sdk-surface.md "What's NOT in the SDK"). Use it directly.
import requests

# SDK imports — never import from apps.* (those are core internals).
# nousviz_sdk is the stable plugin contract.
#
# BaseSyncScript lives at nousviz_sdk.sync — it's not re-exported from the
# package root. Import it from the submodule. Everything else comes from the
# package root.
#
# Imports are bare on purpose. NEVER wrap SDK imports in try/except ImportError:
# the plugin loader surfaces import failures in /system/logs?source=plugin_loader
# with a useful stack. See docs/02-plugin-contract.md "Validator" notes.
from nousviz_sdk.sync import BaseSyncScript
from nousviz_sdk.jobs import heartbeat, check_cancelled
from nousviz_sdk import (
    get_pg_conn,
    get_credential,
    get_connection_field,
    log_event,
)


PLUGIN_SLUG = "google-adsense"

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
ADSENSE_API_BASE = "https://adsense.googleapis.com/v2"

# AdSense report metrics we request, mapped to our column names. Order is
# irrelevant — we resolve values by header name, not position.
METRICS = [
    "ESTIMATED_EARNINGS",
    "PAGE_VIEWS",
    "IMPRESSIONS",
    "CLICKS",
    "IMPRESSIONS_CTR",   # clicks / impressions, as a ratio
    "PAGE_VIEWS_RPM",    # page RPM
]


class GoogleAdsenseSync(BaseSyncScript):
    """One run = refresh the last 30 days of goog_daily from AdSense."""

    plugin_id = PLUGIN_SLUG

    def run(self, since: str | None = None) -> dict[str, Any]:
        # Non-secret config via get_connection_field; secrets via get_credential.
        client_id = get_connection_field(PLUGIN_SLUG, "client_id") or ""
        account_id = get_connection_field(PLUGIN_SLUG, "account_id") or ""
        client_secret = get_credential(PLUGIN_SLUG, "client_secret") or ""
        refresh_token = get_credential(PLUGIN_SLUG, "refresh_token") or ""

        missing = [
            n for n, v in (
                ("client_id", client_id),
                ("client_secret", client_secret),
                ("refresh_token", refresh_token),
                ("account_id", account_id),
            ) if not v
        ]
        if missing:
            raise RuntimeError(
                f"Missing AdSense credentials: {', '.join(missing)}. Have the "
                "operator complete the connection form on the Settings tab."
            )

        self._log("info", "AdSense sync starting")

        # 1. OAuth: exchange the long-lived refresh token for an access token.
        access_token = self._access_token(client_id, client_secret, refresh_token)
        heartbeat(progress={"phase": "authenticated"})

        if check_cancelled():
            self._log("warning", "Sync cancelled by operator before fetch")
            return {"rows_synced": 0, "cancelled": True}

        # 2. Fetch the daily report for the last 30 days.
        rows = self._fetch_daily_report(account_id, access_token)
        heartbeat(progress={"phase": "fetched", "rows_seen": len(rows)})

        # 3. Upsert one row per day.
        rows_written = 0
        for batch in self._batches(rows, size=100):
            if check_cancelled():
                self._log("warning", "Sync cancelled by operator")
                return {"rows_synced": rows_written, "cancelled": True}
            self._upsert_batch(batch)
            rows_written += len(batch)
            heartbeat(progress={
                "phase": "writing",
                "rows_written": rows_written,
                "rows_seen": len(rows),
            })

        self._update_checkpoint(rows_written)
        self._log("info", f"AdSense sync complete: {rows_written} days")
        return {"rows_synced": rows_written}

    # ── OAuth ────────────────────────────────────────────────────────────

    def _access_token(self, client_id: str, client_secret: str, refresh_token: str) -> str:
        resp = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            # Surface Google's error description but never the token payload.
            detail = ""
            try:
                detail = resp.json().get("error_description") or resp.json().get("error", "")
            except Exception:
                detail = resp.text[:200]
            raise RuntimeError(
                f"OAuth token exchange failed (HTTP {resp.status_code}): {detail}"
            )
        token = resp.json().get("access_token")
        if not token:
            raise RuntimeError("OAuth token exchange returned no access_token")
        return token

    # ── Fetch ────────────────────────────────────────────────────────────

    def _fetch_daily_report(self, account_id: str, access_token: str) -> list[dict[str, Any]]:
        """Call reports:generate for the last 30 days, grouped by DATE.

        Returns a list of dicts keyed by our column names, one per day.
        """
        account = account_id if account_id.startswith("accounts/") else f"accounts/{account_id}"
        params = [
            ("dateRange", "LAST_30_DAYS"),
            ("dimensions", "DATE"),
            ("orderBy", "+DATE"),
        ]
        params += [("metrics", m) for m in METRICS]

        resp = requests.get(
            f"{ADSENSE_API_BASE}/{account}/reports:generate",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=60,
        )
        if resp.status_code != 200:
            detail = ""
            try:
                detail = resp.json().get("error", {}).get("message", "")
            except Exception:
                detail = resp.text[:200]
            raise RuntimeError(
                f"AdSense reports:generate failed (HTTP {resp.status_code}): {detail}"
            )

        payload = resp.json()
        headers = [h.get("name", "") for h in payload.get("headers", [])]
        currency = self._report_currency(payload)

        out: list[dict[str, Any]] = []
        for row in payload.get("rows", []):
            cells = [c.get("value", "") for c in row.get("cells", [])]
            by_name = dict(zip(headers, cells))
            report_date = by_name.get("DATE")
            if not report_date:
                continue
            out.append({
                "report_date": report_date,                                  # "YYYY-MM-DD"
                "estimated_earnings": self._num(by_name.get("ESTIMATED_EARNINGS")),
                "page_views": int(self._num(by_name.get("PAGE_VIEWS"))),
                "impressions": int(self._num(by_name.get("IMPRESSIONS"))),
                "clicks": int(self._num(by_name.get("CLICKS"))),
                "ctr": self._num(by_name.get("IMPRESSIONS_CTR")),
                "rpm": self._num(by_name.get("PAGE_VIEWS_RPM")),
                "currency": currency,
                "raw_data": by_name,
            })
        return out

    @staticmethod
    def _report_currency(payload: dict[str, Any]) -> str:
        # AdSense reports carry the account currency at the top level.
        for key in ("currencyCode", "currency"):
            val = payload.get(key)
            if val:
                return str(val)
        return "USD"

    @staticmethod
    def _num(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    # ── Database ─────────────────────────────────────────────────────────

    def _upsert_batch(self, batch: list[dict[str, Any]]) -> None:
        """Idempotent UPSERT keyed on report_date — safe to retry."""
        import json
        with get_pg_conn() as conn:
            cur = conn.cursor()
            for row in batch:
                cur.execute(
                    """
                    INSERT INTO goog_daily (
                        report_date, estimated_earnings, page_views, impressions,
                        clicks, ctr, rpm, currency, raw_data, synced_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now(), now())
                    ON CONFLICT (report_date) DO UPDATE SET
                        estimated_earnings = EXCLUDED.estimated_earnings,
                        page_views = EXCLUDED.page_views,
                        impressions = EXCLUDED.impressions,
                        clicks      = EXCLUDED.clicks,
                        ctr         = EXCLUDED.ctr,
                        rpm         = EXCLUDED.rpm,
                        currency    = EXCLUDED.currency,
                        raw_data    = EXCLUDED.raw_data,
                        synced_at   = EXCLUDED.synced_at,
                        updated_at  = EXCLUDED.updated_at
                    """,
                    (
                        row["report_date"],
                        row["estimated_earnings"],
                        row["page_views"],
                        row["impressions"],
                        row["clicks"],
                        row["ctr"],
                        row["rpm"],
                        row["currency"],
                        json.dumps(row["raw_data"]),
                    ),
                )
            conn.commit()

    def _update_checkpoint(self, rows_written: int) -> None:
        import json
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO goog_sync_state (key, value, updated_at)
                VALUES ('last_sync', %s::jsonb, now())
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = EXCLUDED.updated_at
                """,
                (json.dumps({"rows_written": rows_written}),),
            )
            conn.commit()

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _batches(rows: list, size: int):
        for i in range(0, len(rows), size):
            yield rows[i : i + size]

    def _log(self, level: str, message: str, detail: dict | None = None) -> None:
        """Forward to nousviz_sdk.log_event for structured /system/logs entries."""
        log_event(level, message, detail=detail)


if __name__ == "__main__":
    GoogleAdsenseSync().main()
