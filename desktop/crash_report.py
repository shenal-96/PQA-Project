"""Crash-report emailing for the PQA desktop app (offline-friendly).

The app is fully local with no network/SMTP, so "email the crash logs" means
opening the **user's own mail client** via a ``mailto:`` link pre-addressed to the
developer, with a short summary in the body and the full report written to a file
the user can attach. We also reveal that file in the OS file manager so attaching
is one step.

Everything here is best-effort and never raises into the caller — failing to open
a mail client must not crash the app that is already trying to report a crash.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import urllib.parse
import webbrowser
from datetime import datetime, timezone

from desktop import usage_log

log = logging.getLogger(__name__)

# Keep the mailto body well under the OS URL-length limit (~2000 chars on
# Windows). The full report goes in the attached file; the body is a summary.
_MAILTO_BODY_CHARS = 1200


def _report_filename() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"PQA_crash_report_{stamp}.txt"


def write_report_file(report_text: str) -> str:
    """Write the crash report next to the logs and return its path."""
    path = os.path.join(usage_log.data_dir(), _report_filename())
    with open(path, "w", encoding="utf-8") as f:
        f.write(report_text)
    return path


def build_mailto(subject: str, body: str, to: str | None = None) -> str:
    """Build a ``mailto:`` URL (RFC 6068) with encoded subject + body."""
    to = to or usage_log.DEVELOPER_EMAIL
    query = urllib.parse.urlencode({"subject": subject, "body": body},
                                   quote_via=urllib.parse.quote)
    return f"mailto:{to}?{query}"


def reveal_in_file_manager(path: str) -> bool:
    """Open the OS file manager with ``path`` selected/its folder shown."""
    try:
        if sys.platform == "win32":
            # /select, highlights the file in Explorer.
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path) or "."])
        return True
    except Exception as exc:  # noqa: BLE001
        log.debug("reveal_in_file_manager failed: %s", exc)
        return False


def send_crash_report(app_version: str | None = None, limit: int = 20,
                      reveal: bool = True) -> dict:
    """Assemble the report, write it to a file, and open the mail client.

    Returns a JSON-safe dict the frontend can act on::

        {"ok": bool, "email": str, "report_path": str | None,
         "mailto_opened": bool, "revealed": bool, "error": str | None}

    Clears the pending-crash marker on a successful mail-client launch so the
    user isn't re-prompted on the next start.
    """
    result = {
        "ok": False,
        "email": usage_log.DEVELOPER_EMAIL,
        "report_path": None,
        "mailto_opened": False,
        "revealed": False,
        "error": None,
    }
    try:
        report = usage_log.build_crash_report(limit=limit, app_version=app_version)

        path = None
        try:
            path = write_report_file(report)
            result["report_path"] = path
        except Exception as exc:  # noqa: BLE001 — still try the mailto body
            log.debug("could not write crash report file: %s", exc)

        pending = usage_log.has_pending_crash() or {}
        subject = "PQA Desktop crash report"
        if pending.get("error_type"):
            subject += f" — {pending['error_type']}"

        body_lines = [
            "Hi,",
            "",
            "PQA Desktop encountered a problem. The full diagnostic report is "
            "attached" + (f" (saved at: {path})" if path else "") + ".",
            "",
            "--- report preview ---",
            report[:_MAILTO_BODY_CHARS],
        ]
        if len(report) > _MAILTO_BODY_CHARS:
            body_lines.append("... (truncated — see attached file for the full report)")
        mailto = build_mailto(subject, "\n".join(body_lines))

        try:
            result["mailto_opened"] = bool(webbrowser.open(mailto))
        except Exception as exc:  # noqa: BLE001
            log.debug("webbrowser.open(mailto) failed: %s", exc)

        if reveal and path:
            result["revealed"] = reveal_in_file_manager(path)

        usage_log.clear_pending_crash()
        result["ok"] = True
    except Exception as exc:  # noqa: BLE001 — reporting must never crash the app
        log.debug("send_crash_report failed: %s", exc)
        result["error"] = str(exc)
    return result
