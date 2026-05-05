"""
Lightweight telemetry — usage events, error logs, and crash reports
shipped to a Google Sheets webhook.

Design notes:
- Silent-fail by design. Tracking must never crash or block the app.
- Events fire on a daemon thread so the UI is never blocked by network IO.
- IPs are hashed with a salt before send; raw IPs are never persisted.
- If the webhook secret is missing, calls become no-ops.

Required Streamlit secrets (set in Streamlit Cloud → Settings → Secrets):
    TELEMETRY_WEBHOOK = "https://script.google.com/macros/s/.../exec"
    TELEMETRY_SALT    = "any-random-string-pick-once-and-keep"
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
import threading
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

import streamlit as st

log = logging.getLogger("PQA.tracking")

_TIMEOUT_S = 5.0
_USER_HASH_LEN = 12
_SESSION_FLAG = "_telemetry_app_open_logged"
_PRESET_FLAG = "_telemetry_last_preset"


def _get_secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


def _client_ip() -> str:
    try:
        headers = st.context.headers
        xff = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        real_ip = headers.get("X-Real-Ip") or headers.get("x-real-ip")
        if real_ip:
            return real_ip
    except Exception:
        pass
    return "local"


def _user_hash() -> str:
    salt = _get_secret("TELEMETRY_SALT", "pqa-default-salt")
    raw = f"{_client_ip()}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:_USER_HASH_LEN]


def _app_version() -> str:
    try:
        return str(st.session_state.get("_build_version", "")) or "unknown"
    except Exception:
        return "unknown"


def _post(url: str, payload: dict[str, Any]) -> None:
    try:
        body = json.dumps(payload, default=str).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            resp.read()
    except Exception as exc:
        log.debug(f"telemetry post failed (silent): {exc}")


def _send(sheet: str, **fields: Any) -> None:
    url = _get_secret("TELEMETRY_WEBHOOK", "")
    if not url:
        return
    try:
        payload = {
            "sheet": sheet,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_hash": _user_hash(),
            "app_version": _app_version(),
            **fields,
        }
        threading.Thread(target=_post, args=(url, payload), daemon=True).start()
    except Exception as exc:
        log.debug(f"telemetry send failed (silent): {exc}")


def log_event(event_type: str, **details: Any) -> None:
    """Record a usage event in the 'usage' sheet."""
    _send("usage", event_type=event_type,
          details=json.dumps(details, default=str) if details else "")


def log_error(category: str, message: str, **details: Any) -> None:
    """Record a non-fatal error (validation failures, parse errors, etc.)."""
    _send("errors", category=category, message=str(message)[:500],
          details=json.dumps(details, default=str) if details else "")


def log_crash(exc: BaseException, context: str = "") -> None:
    """Record an uncaught exception with full traceback."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    _send("crashes",
          error_type=type(exc).__name__,
          message=str(exc)[:500],
          context=context,
          traceback=tb[:5000])


def log_app_open_once() -> None:
    """Fire app_open once per Streamlit session."""
    try:
        if not st.session_state.get(_SESSION_FLAG):
            st.session_state[_SESSION_FLAG] = True
            log_event("app_open")
    except Exception:
        pass


def log_preset_change(current: str) -> None:
    """Fire preset_changed only when the active preset actually changes."""
    try:
        last = st.session_state.get(_PRESET_FLAG)
        if last is None:
            st.session_state[_PRESET_FLAG] = current
            return
        if last != current:
            st.session_state[_PRESET_FLAG] = current
            log_event("preset_changed", preset=current)
    except Exception:
        pass


def install_global_handlers() -> None:
    """Install sys.excepthook once to capture uncaught crashes."""
    if getattr(install_global_handlers, "_installed", False):
        return
    install_global_handlers._installed = True

    prior = sys.excepthook

    def _excepthook(exc_type, exc_value, exc_tb):
        try:
            log_crash(exc_value, context="sys.excepthook")
        except Exception:
            pass
        prior(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook
