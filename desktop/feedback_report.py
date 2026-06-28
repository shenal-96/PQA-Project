"""In-app feedback (feature requests / bug reports) for the PQA desktop app.

The app is fully local with no network/SMTP, so "email the developer" means
opening the **user's own mail client** via a ``mailto:`` link pre-addressed to
the developer, with the user's message in the body. This mirrors
``crash_report.py`` — feedback just carries no attachment, so it is simpler.

Everything here is best-effort and never raises into the caller — failing to
open a mail client must not crash the app.
"""
from __future__ import annotations

import logging
import urllib.parse
import webbrowser

from desktop import usage_log

log = logging.getLogger(__name__)

# Keep the mailto body under the OS URL-length limit (~2000 chars on Windows).
_MAILTO_BODY_CHARS = 1500

# Human labels + subject lines per feedback kind.
_KINDS = {
    "feature": ("Feature request", "PQA Desktop — Feature request"),
    "bug": ("Bug report", "PQA Desktop — Bug report"),
}


def build_mailto(subject: str, body: str, to: str | None = None) -> str:
    """Build a ``mailto:`` URL (RFC 6068) with encoded subject + body."""
    to = to or usage_log.DEVELOPER_EMAIL
    query = urllib.parse.urlencode({"subject": subject, "body": body},
                                   quote_via=urllib.parse.quote)
    return f"mailto:{to}?{query}"


def send_feedback(kind: str, message: str, app_version: str | None = None) -> dict:
    """Open the user's mail client with a feature request / bug report.

    ``kind`` is ``"feature"`` or ``"bug"``; ``message`` is the user's text.
    Returns a JSON-safe dict the frontend can act on::

        {"ok": bool, "email": str, "mailto_opened": bool, "error": str | None}

    Fully offline — no data is sent anywhere automatically; the user chooses to
    send the email their mail client opens with.
    """
    result = {
        "ok": False,
        "email": usage_log.DEVELOPER_EMAIL,
        "mailto_opened": False,
        "error": None,
    }
    try:
        label, subject = _KINDS.get(str(kind).lower(), _KINDS["feature"])

        text = (message or "").strip()
        if not text:
            result["error"] = "empty message"
            return result
        text = text[:_MAILTO_BODY_CHARS]

        body_lines = [
            f"{label} for PQA Desktop ({app_version or 'unknown'}):",
            "",
            text,
            "",
            "---",
            "Sent from the PQA Desktop app.",
        ]
        mailto = build_mailto(subject, "\n".join(body_lines))

        try:
            result["mailto_opened"] = bool(webbrowser.open(mailto))
        except Exception as exc:  # noqa: BLE001
            log.debug("webbrowser.open(mailto) failed: %s", exc)

        result["ok"] = True
    except Exception as exc:  # noqa: BLE001 — feedback must never crash the app
        log.debug("send_feedback failed: %s", exc)
        result["error"] = str(exc)
    return result
