"""Local, persistent usage + error logging for the PQA desktop app.

Tracks lightweight per-user usage counters — **analyses run**, **reports
generated**, and **time spent in the app** — in a small JSON file on the local
machine, plus an append-only **error/crash log** (with tracebacks) in a sibling
``error_log.jsonl``. Nothing leaves the device; this is purely a local record the
owner can inspect.

**Where it lives (and why it survives updates).** The log is written to the
per-user *application-data* directory, **not** the install directory. On Windows
the app is installed under ``Program Files`` (via the Inno Setup installer), and
that tree is replaced wholesale on every update/reinstall — anything stored there
would be wiped. ``%APPDATA%\\PQA`` (roaming app data) is owned by the user, lives
outside the install tree, and is left untouched by installs/uninstalls, so the
usage history accumulates across versions. Equivalent per-user locations are used
on macOS/Linux so the module is testable off-Windows. Set ``PQA_DATA_DIR`` to
override (used by the tests).

**Safety posture (mirrors ``tracking.py``).** Logging must never crash or block
the app. Every public function swallows its own exceptions and degrades to a
no-op; a corrupt or unreadable file is treated as empty rather than fatal. Writes
are atomic (temp file + ``os.replace``) and guarded by a process-wide lock so the
periodic session flush and the bridge counters can't interleave a half-written
file.

Users are keyed by the OS account name (``getpass.getuser()``) so a shared
machine keeps a separate tally per Windows user.
"""
from __future__ import annotations

import getpass
import json
import logging
import os
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_LOG_FILENAME = "usage_log.json"
_ERROR_LOG_FILENAME = "error_log.jsonl"
_APP_DIR_NAME = "PQA"

# Cap the append-only error log so it can't grow without bound. When it exceeds
# this size we keep the most recent ``_ERROR_LOG_KEEP_LINES`` entries.
_ERROR_LOG_MAX_BYTES = 1_000_000
_ERROR_LOG_KEEP_LINES = 500

# Serialises every read-modify-write so concurrent callers (the bridge counters
# and the background session-time flush) never corrupt the file.
_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def data_dir() -> str:
    """Return the persistent per-user data directory, creating it if needed.

    Resolution order:

    1. ``$PQA_DATA_DIR`` if set (explicit override; used by tests).
    2. Windows: ``%APPDATA%\\PQA`` (roaming) or ``%LOCALAPPDATA%\\PQA``.
    3. macOS: ``~/Library/Application Support/PQA``.
    4. Linux/other: ``$XDG_DATA_HOME/PQA`` or ``~/.local/share/PQA``.

    Falls back to ``~/.pqa`` if the preferred base is unavailable.
    """
    override = os.environ.get("PQA_DATA_DIR")
    if override:
        base = override
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        base = os.path.join(base, _APP_DIR_NAME) if base else None
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library",
                            "Application Support", _APP_DIR_NAME)
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = (os.path.join(xdg, _APP_DIR_NAME) if xdg
                else os.path.join(os.path.expanduser("~"), ".local", "share", _APP_DIR_NAME))

    if not base:
        base = os.path.join(os.path.expanduser("~"), ".pqa")

    os.makedirs(base, exist_ok=True)
    return base


def log_path() -> str:
    """Absolute path to the usage-log JSON file."""
    return os.path.join(data_dir(), _LOG_FILENAME)


def error_log_path() -> str:
    """Absolute path to the append-only error/crash JSONL file."""
    return os.path.join(data_dir(), _ERROR_LOG_FILENAME)


def _current_user() -> str:
    try:
        return getpass.getuser() or "unknown"
    except Exception:  # noqa: BLE001 — getuser can raise if no account info
        return "unknown"


def _blank_user(now: str) -> dict:
    return {
        "analyses_run": 0,
        "reports_generated": 0,
        "active_seconds": 0.0,
        "sessions": 0,
        "first_seen": now,
        "last_seen": now,
    }


def _read_raw() -> dict:
    """Load the log file, returning a fresh skeleton on any problem."""
    try:
        with open(log_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "users" not in data:
            raise ValueError("malformed usage log")
        data.setdefault("version", _SCHEMA_VERSION)
        if not isinstance(data.get("users"), dict):
            data["users"] = {}
        return data
    except FileNotFoundError:
        return {"version": _SCHEMA_VERSION, "users": {}}
    except Exception as exc:  # noqa: BLE001 — corrupt/unreadable -> start clean
        log.debug("usage log unreadable, starting fresh: %s", exc)
        return {"version": _SCHEMA_VERSION, "users": {}}


def _write_atomic(data: dict) -> None:
    """Write ``data`` to the log file atomically (temp file + replace)."""
    path = log_path()
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".usage_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _bump(user: str | None = None, **deltas) -> None:
    """Apply numeric ``deltas`` to ``user``'s record and refresh ``last_seen``.

    Never raises — failures are logged at debug and dropped so callers in hot
    paths (analysis, report generation) can call this unconditionally.
    """
    try:
        with _LOCK:
            data = _read_raw()
            now = _now_iso()
            uname = user or _current_user()
            rec = data["users"].get(uname) or _blank_user(now)
            for key, delta in deltas.items():
                rec[key] = (rec.get(key) or 0) + delta
            rec["last_seen"] = now
            rec.setdefault("first_seen", now)
            data["users"][uname] = rec
            _write_atomic(data)
    except Exception as exc:  # noqa: BLE001 — usage logging must never crash the app
        log.debug("usage log update failed: %s", exc)


# --- public counters -------------------------------------------------------
def record_analysis_run(user: str | None = None) -> None:
    """Increment the analysis-run counter for the current (or given) user."""
    _bump(user, analyses_run=1)


def record_report_generated(user: str | None = None) -> None:
    """Increment the report-generated counter for the current (or given) user."""
    _bump(user, reports_generated=1)


def record_session_start(user: str | None = None) -> None:
    """Increment the session counter (call once when the app window opens)."""
    _bump(user, sessions=1)


def record_active_seconds(seconds: float, user: str | None = None) -> None:
    """Add ``seconds`` of app-active time to the current (or given) user."""
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return
    if seconds <= 0:
        return
    _bump(user, active_seconds=seconds)


# --- read-out --------------------------------------------------------------
def read_usage() -> dict:
    """Return the full usage log as a plain dict (for display/export).

    Adds a convenience ``active_hours`` field per user. Returns an empty
    skeleton if anything goes wrong.
    """
    try:
        with _LOCK:
            data = _read_raw()
        for rec in data.get("users", {}).values():
            rec["active_hours"] = round((rec.get("active_seconds") or 0) / 3600.0, 3)
        return data
    except Exception as exc:  # noqa: BLE001
        log.debug("usage log read failed: %s", exc)
        return {"version": _SCHEMA_VERSION, "users": {}}


# --- error / crash logging -------------------------------------------------
def _append_error(entry: dict) -> None:
    """Append one JSON entry to the error log, rotating if it grew too large."""
    try:
        with _LOCK:
            path = error_log_path()
            # Rotate: if the file is over the cap, keep only the most recent lines.
            try:
                if os.path.getsize(path) > _ERROR_LOG_MAX_BYTES:
                    with open(path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    kept = lines[-_ERROR_LOG_KEEP_LINES:]
                    with open(path, "w", encoding="utf-8") as f:
                        f.writelines(kept)
            except FileNotFoundError:
                pass
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")
            # Keep a rolling count of errors on the user's usage record too, so
            # usage_summary surfaces "this user has hit N errors" at a glance.
            _bump(entry.get("user"), errors_logged=1)
    except Exception as exc:  # noqa: BLE001 — error logging must never raise
        log.debug("error log append failed: %s", exc)


def log_error(category: str, message: str, user: str | None = None, **details) -> None:
    """Record a handled error (no traceback) in the local error log.

    ``category`` is a short bucket (e.g. ``"csv_format_invalid"``); ``message``
    is human-readable; ``details`` are extra JSON-safe context fields.
    """
    _append_error({
        "timestamp": _now_iso(),
        "user": user or _current_user(),
        "type": "error",
        "category": str(category),
        "message": str(message)[:2000],
        "details": {k: str(v)[:500] for k, v in details.items()},
    })


def log_crash(exc: BaseException, context: str = "", user: str | None = None) -> None:
    """Record an exception with its full traceback in the local error log."""
    try:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    except Exception:  # noqa: BLE001 — formatting a broken exc must not re-raise
        tb = repr(exc)
    _append_error({
        "timestamp": _now_iso(),
        "user": user or _current_user(),
        "type": "crash",
        "error_type": type(exc).__name__,
        "message": str(exc)[:2000],
        "context": str(context)[:500],
        "traceback": tb[:8000],
    })


def read_errors(limit: int = 100) -> list[dict]:
    """Return the most recent error/crash entries (newest last), up to ``limit``."""
    try:
        with _LOCK:
            with open(error_log_path(), "r", encoding="utf-8") as f:
                lines = f.readlines()
        out = []
        for line in lines[-int(limit):]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
    except FileNotFoundError:
        return []
    except Exception as exc:  # noqa: BLE001
        log.debug("error log read failed: %s", exc)
        return []


def install_global_handlers() -> None:
    """Install ``sys.excepthook`` + ``threading.excepthook`` wrappers.

    Uncaught exceptions on the main thread or in worker threads (e.g. the
    session-timer daemon) are logged to the local crash log before the prior
    hook runs, so a real crash leaves a record the owner can inspect. Re-running
    this is safe — it chains onto whatever hook is currently installed.
    """
    try:
        prev_hook = sys.excepthook

        def _hook(exc_type, exc, tb):
            try:
                log_crash(exc if isinstance(exc, BaseException) else Exception(str(exc)),
                          context="sys.excepthook")
            finally:
                prev_hook(exc_type, exc, tb)

        sys.excepthook = _hook
    except Exception as exc:  # noqa: BLE001
        log.debug("failed to install sys.excepthook: %s", exc)

    try:
        prev_thread_hook = threading.excepthook

        def _thread_hook(args):
            try:
                if args.exc_value is not None:
                    log_crash(args.exc_value, context=f"thread:{args.thread.name}")
            finally:
                prev_thread_hook(args)

        threading.excepthook = _thread_hook
    except Exception as exc:  # noqa: BLE001
        log.debug("failed to install threading.excepthook: %s", exc)


# --- session timer ---------------------------------------------------------
class SessionTimer:
    """Accumulates app-active time and flushes it to the log periodically.

    A background daemon thread adds elapsed wall-clock time to the user's
    ``active_seconds`` every ``flush_interval_s`` (default 60 s), so a crash
    loses at most one interval rather than the whole session. Call
    :meth:`start` when the window opens and :meth:`stop` when it closes (the
    close handler does a final flush).

    Wall-clock is used via :func:`time.monotonic`; the timer makes no attempt to
    detect idle/minimised states — "time spent in the app" means the window was
    open.
    """

    def __init__(self, flush_interval_s: float = 60.0, user: str | None = None) -> None:
        self._interval = max(5.0, float(flush_interval_s))
        self._user = user
        self._last = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _elapsed_since_last(self) -> float:
        now = time.monotonic()
        if self._last is None:
            self._last = now
            return 0.0
        delta = now - self._last
        self._last = now
        return delta

    def _flush(self) -> None:
        record_active_seconds(self._elapsed_since_last(), self._user)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self._flush()

    def start(self) -> None:
        """Begin counting; records a session start and arms the flush thread."""
        try:
            self._last = time.monotonic()
            record_session_start(self._user)
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            name="pqa-usage-timer")
            self._thread.start()
        except Exception as exc:  # noqa: BLE001
            log.debug("usage session timer failed to start: %s", exc)

    def stop(self) -> None:
        """Stop counting and flush the final partial interval."""
        try:
            self._stop.set()
            self._flush()
        except Exception as exc:  # noqa: BLE001
            log.debug("usage session timer failed to stop cleanly: %s", exc)
