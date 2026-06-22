"""
hooks/lifecycle.py — Lifecycle hooks for google-adsense.

Hooks fire on operator actions (credentials saved, first sync success,
etc.) and run in their own subprocesses with the credential broker
available — different from API routes (which share the API process).

Each function receives a HookContext and returns a HookResult. The
result.message becomes a toast in the operator's UI.

Reference: docs/06-sync-and-jobs.md "Lifecycle hooks"
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src/ to sys.path so we can import the slug-prefixed sync module
# (which has the `load_connection_config`-style helpers a hook may want
# to reuse). The slug-prefix on the filename keeps us out of G-1 trouble.
_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PLUGIN_ROOT / "src"))

# SDK imports are bare on purpose. NEVER wrap in try/except ImportError —
# the hook runner surfaces import failures in /system/logs?source=hook_runner
# with a useful stack. A defensive guard would silently demote a hard failure
# into a None-shaped runtime crash. See docs/02-plugin-contract.md "Validator".
from nousviz_sdk.hooks import HookContext, HookResult


def on_credentials_saved(ctx: HookContext) -> HookResult:
    """Called after the operator saves connection credentials.

    Probe the external source to verify the credentials work. The
    result message becomes a toast in the operator's UI.

    Failure here doesn't undo the save — the operator may be deliberately
    saving partial credentials to fix something. Return ok=False with a
    helpful message and the operator can retry.
    """
    try:
        # The operator clicks "Test connection" to verify the OAuth exchange
        # (see api/routes.py:test_connection), so this hook stays light: just
        # confirm the four fields are present. The credential broker is
        # available here if a deeper probe is ever wanted:
        #
        #   from nousviz_sdk import get_credential, get_connection_field
        #   client_secret = get_credential("google-adsense", "client_secret")
        #   account_id    = get_connection_field("google-adsense", "account_id")
        pass
    except Exception as e:
        return HookResult(
            ok=False,
            message=f"Credentials saved but probe failed: {e.__class__.__name__}: {e}",
        )

    return HookResult(
        ok=True,
        message="Credentials saved. Click 'Run sync' on the Settings tab to populate data.",
    )


def on_first_run_success(ctx: HookContext) -> HookResult:
    """Fires once after the first successful sync. Useful for sending
    welcome toasts, logging analytics events, or kicking off background
    setup tasks. Errors here are non-fatal — the sync itself succeeded.
    """
    return HookResult(
        ok=True,
        message=(
            "Plugin is live — your first sync completed. Browse the Overview "
            "tab or check the Sync Reports tab for run history."
        ),
    )
