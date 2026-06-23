"""
api/routes.py — HTTP routes for google-adsense.

Routes are mounted at /api/plugins/<slug>/* by the plugin loader. The
file MUST export a `router` variable (a FastAPI APIRouter).

Patterns demonstrated here:
- DictCursor used correctly: DictCursor(conn.cursor()), NOT
  conn.cursor(cursor_factory=DictCursor). See appendix-gotchas.md G-2.
- Action handlers that write job_runs rows so the setup-checklist
  predicates flip. See docs/06-sync-and-jobs.md.
- Parameterised queries always — never f-strings, never .format().
- Belt-and-braces auth: Depends(_require_analyst) on every data route
  (the middleware also gates these, but plugins ship defense-in-depth —
  see docs/03-data-and-routes.md and CLAUDE.md).
- Structured logging via log_event for failures.

Reference: docs/03-data-and-routes.md
"""

from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, timezone
from typing import Any

import requests
from fastapi import APIRouter, Depends, HTTPException, Request

# SDK contract — never import from apps.*. Bare imports on purpose: a defensive
# try/except ImportError demotes a hard load failure into a silent runtime
# crash. The plugin loader surfaces real import errors in
# /system/logs?source=plugin_loader. See docs/07-shipping-and-operator-flow.md.
from nousviz_sdk import (
    get_pg_conn,
    DictCursor,
    get_credential,
    get_connection_field,
    log_event,
)


router = APIRouter()
PLUGIN_SLUG = "google-adsense"
BASE = f"/plugins/{PLUGIN_SLUG}"
PLUGIN_VERSION = "0.2.0"   # bump alongside plugin.yaml.version

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_analyst(request: Request) -> str:
    """Reject if the caller isn't an authenticated NousViz user.

    The auth middleware already gates /api/plugins/* (v0.9.4.9+); this is
    belt-and-braces defense-in-depth on data-bearing routes. The middleware
    sets request.state.user_identity. See docs/03-data-and-routes.md
    "Belt-and-braces auth on individual routes".
    """
    identity = getattr(request.state, "user_identity", None)
    if not identity:
        raise HTTPException(status_code=401, detail="Auth required")
    return identity


def _record_action_run(
    *, job_id: str, status: str, duration_ms: int, detail: dict[str, Any]
) -> None:
    """Write a job_runs row so action handlers advance the setup checklist.

    The `last_test_success` predicate looks at the most recent terminal status
    of a job_runs row matching `hook:<slug>:test_connection`.
    """
    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO job_runs (
                    job_id, status, source, started_at, completed_at,
                    duration_ms, details
                )
                VALUES (%s, %s, 'manual', now(), now(), %s, %s::jsonb)
                """,
                (job_id, status, duration_ms, json.dumps(detail)),
            )
            conn.commit()
    except Exception as exc:
        # Don't bring down the action just because audit logging failed.
        log_event(
            "warning",
            f"Failed to write job_runs row for {job_id}",
            detail={"error": str(exc)},
        )


# ── Health ──────────────────────────────────────────────────────────────────


@router.get(f"{BASE}/health-check")
def health_check() -> dict[str, Any]:
    """Liveness endpoint. Operators / scripts hit this to confirm the
    deployed version of the plugin matches what was tagged. See
    docs/08-sop-and-discipline.md "Verify deployed = tagged".
    """
    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*), max(report_date) FROM goog_daily")
            n, latest = cur.fetchone()
            cur.execute("SELECT value->>'amount' FROM goog_sync_state WHERE key = 'balance'")
            brow = cur.fetchone()
        return {
            "plugin": PLUGIN_SLUG,
            "version": PLUGIN_VERSION,
            "ok": True,
            "days_count": n,
            "latest_report_date": latest.isoformat() if latest else None,
            "current_balance": (brow[0] if brow else None),
            "as_of": _now_iso(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {e}")


# ── Action: Test connection ─────────────────────────────────────────────────


@router.post(f"{BASE}/test-connection")
def test_connection() -> dict[str, Any]:
    """Probe AdSense by exchanging the refresh token for an access token.

    A successful OAuth exchange proves the four credentials are coherent
    without pulling a full report. Writes a job_runs row so the operator's
    `last_test_success` setup-checklist predicate flips.
    """
    started = time.monotonic()

    try:
        client_id = get_connection_field(PLUGIN_SLUG, "client_id") or ""
        client_secret = get_credential(PLUGIN_SLUG, "client_secret") or ""
        refresh_token = get_credential(PLUGIN_SLUG, "refresh_token") or ""
        account_id = get_connection_field(PLUGIN_SLUG, "account_id") or ""

        if not all([client_id, client_secret, refresh_token, account_id]):
            return {
                "ok": False,
                "level": "warning",
                "toast": "Fill in Client ID, Client secret, Refresh token, and Account ID first.",
            }

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
        if resp.status_code != 200 or not resp.json().get("access_token"):
            try:
                detail = resp.json().get("error_description") or resp.json().get("error", "")
            except Exception:
                detail = resp.text[:120]
            raise RuntimeError(f"OAuth exchange failed (HTTP {resp.status_code}): {detail}")

    except Exception as e:
        cls = e.__class__.__name__
        msg = str(e)
        tb = traceback.format_exc()[-1500:]
        duration_ms = int((time.monotonic() - started) * 1000)

        _record_action_run(
            job_id=f"hook:{PLUGIN_SLUG}:test_connection",
            status="error",
            duration_ms=duration_ms,
            detail={"stage": "oauth_probe", "error": f"{cls}: {msg}", "traceback_tail": tb},
        )
        log_event(
            "error",
            f"AdSense test connection failed: {cls}",
            detail={"error": msg, "traceback_tail": tb},
        )
        return {
            "ok": False,
            "level": "error",
            "toast": f"Test connection: {cls}: {msg[:100]}",
        }

    duration_ms = int((time.monotonic() - started) * 1000)
    _record_action_run(
        job_id=f"hook:{PLUGIN_SLUG}:test_connection",
        status="success",
        duration_ms=duration_ms,
        detail={"stage": "oauth_probe", "ok": True},
    )
    return {
        "ok": True,
        "level": "info",
        "toast": "Connection OK — AdSense credentials authenticated.",
        "duration_ms": duration_ms,
    }


# ── Action: Run sync ────────────────────────────────────────────────────────


@router.post(f"{BASE}/sync-now")
def sync_now() -> dict[str, Any]:
    """Enqueue a sync. Plugin declares execution_mode: async, so this
    inserts a queued job_runs row; the jobs-worker claims it. Returns
    immediately — never call the sync function directly from a route
    (10-minute HTTP timeout will kill long syncs).
    """
    job_id = f"sync:{PLUGIN_SLUG}"

    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()

            # Defence-in-depth check (concurrency_policy: skip_if_running
            # also prevents this at the scheduler level).
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM job_runs
                    WHERE job_id = %s
                      AND status IN ('queued', 'running', 'cancelling', 'paused')
                )
                """,
                (job_id,),
            )
            (active,) = cur.fetchone()
            if active:
                return {
                    "level": "warning",
                    "toast": "A sync is already running. Watch the Overview tab.",
                    "navigate": f"/plugin/{PLUGIN_SLUG}/overview",
                }

            cur.execute(
                """
                INSERT INTO job_runs (job_id, status, source, started_at, details)
                VALUES (%s, 'queued', 'manual', now(), %s::jsonb)
                RETURNING id
                """,
                (job_id, json.dumps({"via": "plugin_action"})),
            )
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                raise RuntimeError("INSERT into job_runs returned no row")
            run_id = row[0]
            conn.commit()

        return {
            "level": "info",
            "toast": f"Sync queued (job #{run_id}). Watch the Overview tab.",
            "navigate": f"/plugin/{PLUGIN_SLUG}/overview",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not enqueue sync: {e}")


# ── Data routes ─────────────────────────────────────────────────────────────


@router.get(f"{BASE}/kpis")
def kpis(_: str = Depends(_require_analyst)) -> dict[str, Any]:
    """The four headline KPIs over the last 30 days, in one round-trip."""
    with get_pg_conn() as conn:
        cur = DictCursor(conn.cursor())   # Correct DictCursor pattern (G-2)
        cur.execute("""
            SELECT
                COALESCE(SUM(estimated_earnings), 0)             AS earnings_30d,
                COALESCE(SUM(clicks), 0)                         AS clicks_30d,
                COALESCE(ROUND(AVG(NULLIF(rpm, 0)), 2), 0)       AS avg_rpm,
                MAX(currency)                                    AS currency
            FROM goog_daily
            WHERE report_date >= (CURRENT_DATE - INTERVAL '30 days')
        """)
        stats = dict(cur.fetchone() or {})

        cur.execute("""
            SELECT FLOOR(EXTRACT(EPOCH FROM (now() - MAX(completed_at))) / 60)::bigint AS minutes
            FROM job_runs
            WHERE job_id = %s AND status = 'success'
        """, (f"sync:{PLUGIN_SLUG}",))
        last = cur.fetchone()
        stats["last_sync_minutes_ago"] = (last["minutes"] if last else None)

    return {"stats": stats, "data_as_of": _now_iso()}


@router.get(f"{BASE}/daily")
def daily(_: str = Depends(_require_analyst)) -> dict[str, Any]:
    """Daily earnings series (last 30 days), oldest first — line-chart shape."""
    with get_pg_conn() as conn:
        cur = DictCursor(conn.cursor())
        cur.execute("""
            SELECT
                to_char(report_date, 'YYYY-MM-DD') AS date,
                estimated_earnings                 AS earnings,
                clicks,
                impressions,
                rpm
            FROM goog_daily
            WHERE report_date >= (CURRENT_DATE - INTERVAL '30 days')
            ORDER BY report_date ASC
        """)
        rows = [dict(r) for r in cur.fetchall()]
    return {"rows": rows, "data_as_of": _now_iso()}
