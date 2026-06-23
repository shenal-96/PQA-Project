"""PyWebview desktop shell + the JS<->Python HostBridge.

The shell opens a native window backed by Edge **WebView2** (Chromium) and loads
the locally-bundled web UI from disk. JS calls Python through PyWebview's
in-process bridge (``window.pywebview.api.*``) — there is **no web server and no
network**. Everything (analysis, plots, reports) runs in this process.

``HostBridge`` deliberately imports nothing GUI-related at module load, so it can
be unit-tested under plain CPython (see ``tests/test_hostbridge.py``). Only
``main()`` imports ``webview``.
"""
from __future__ import annotations

import base64
import dataclasses
import functools
import io
import os
import sys

from desktop import usage_log


def _logged(method):
    """Wrap a bridge method so any exception is recorded in the local crash log.

    The exception is re-raised unchanged so the frontend still sees the error;
    we just leave a durable record (with traceback) in ``error_log.jsonl`` first.
    Logging is best-effort and never masks the original failure.
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — log then re-raise
            usage_log.log_crash(exc, context=method.__name__)
            raise
    return wrapper


class HostBridge:
    """Methods here are exposed to JS as ``window.pywebview.api.<name>(...)``.

    Only JSON-serialisable args/returns cross the bridge. The last loaded frame
    and analysis result are cached so follow-up calls (charts, recalculation,
    reports) reuse them.
    """

    def __init__(self) -> None:
        self._df = None          # full raw loaded frame (kept so the time window can be re-applied)
        self._df_run = None      # the (possibly time-windowed) frame the last analysis ran on
        self._df_proc = None     # processed frame
        self._df_events = None   # detected events
        self._config = None      # AnalysisConfig used for the last run

    # ---- capabilities -----------------------------------------------------
    def caps(self) -> dict:
        """Platform capability flags the frontend gates features on."""
        return {"platform": "desktop", "canReport": True, "canXls": True}

    # ---- usage log --------------------------------------------------------
    def usage_summary(self) -> dict:
        """Return local usage counters (analyses, reports, hours) per user.

        Read-only view of the persistent local usage log
        (``%APPDATA%\\PQA\\usage_log.json`` on Windows). Nothing leaves the
        machine — this just surfaces the stored tally for display/export.
        """
        return usage_log.read_usage()

    def recent_errors(self, params: dict | None = None) -> dict:
        """Return the most recent local error/crash log entries (with tracebacks).

        Read-only view of ``%APPDATA%\\PQA\\error_log.jsonl``. ``params`` may
        carry ``{"limit": int}`` (default 100). Nothing leaves the machine.
        """
        limit = int((params or {}).get("limit", 100))
        return {"errors": usage_log.read_errors(limit)}

    # ---- crash reporting --------------------------------------------------
    def pending_crash(self) -> dict:
        """Report whether a prior run crashed without the report being sent.

        The frontend calls this on startup; if ``pending`` is non-null it offers
        the user the option to email the crash logs to the developer.
        """
        return {"pending": usage_log.has_pending_crash(),
                "email": usage_log.DEVELOPER_EMAIL}

    def crash_report_preview(self, params: dict | None = None) -> dict:
        """Return the assembled crash-report text (for showing before sending)."""
        limit = int((params or {}).get("limit", 20))
        return {"report": usage_log.build_crash_report(limit=limit),
                "email": usage_log.DEVELOPER_EMAIL}

    def email_crash_report(self, params: dict | None = None) -> dict:
        """Open the user's mail client pre-addressed to the developer.

        Writes the full report to a file (returned in ``report_path``), opens a
        ``mailto:`` with a summary, reveals the file so the user can attach it,
        and clears the pending-crash marker. Fully offline — no data is sent
        anywhere automatically; the user chooses to send the email.
        """
        from desktop.crash_report import send_crash_report

        params = params or {}
        return send_crash_report(limit=int(params.get("limit", 20)),
                                 reveal=bool(params.get("reveal", True)))

    def dismiss_crash_report(self) -> dict:
        """Clear the pending-crash marker without emailing (user declined)."""
        usage_log.clear_pending_crash()
        return {"ok": True}

    # ---- CSV ingest -------------------------------------------------------
    @_logged
    def load_csv(self, params: dict | None = None) -> dict:
        """Load a CSV and validate it.

        ``params`` is a single dict (PyWebview passes one JS object across the
        bridge): ``{"csv_b64": str, "csv_text": str, "filename": str}``. Base64
        bytes are preferred; raw text is accepted as a fallback.
        """
        import core.analysis as ca

        params = params or {}
        csv_b64 = params.get("csv_b64")
        csv_text = params.get("csv_text")
        filename = params.get("filename")

        if csv_b64 is not None:
            raw = base64.b64decode(csv_b64)
        elif csv_text is not None:
            raw = csv_text.encode("utf-8", errors="replace")
        else:
            raise ValueError("load_csv requires csv_b64 or csv_text")

        self._df = ca.load_and_prepare_csv(io.BytesIO(raw))
        self._df_run = self._df_proc = self._df_events = self._config = None
        ok, errors, warnings = ca.validate_csv_format(self._df)
        t_min, t_max = self._time_range()
        return {
            "filename": filename,
            "logger_format": self._df.attrs.get("logger_format"),
            "n_rows": int(len(self._df)),
            "columns": [str(c) for c in self._df.columns],
            "time_min": t_min,
            "time_max": t_max,
            "valid": bool(ok),
            "errors": errors,
            "warnings": warnings,
        }

    # ---- WinScope XLS ingest ---------------------------------------------
    @_logged
    def load_winscope(self, params: dict | None = None) -> dict:
        """Load a WinScope ``.xls`` export and validate it (mirrors ``load_csv``).

        ``params``: ``{"b64": str, "filename": str}``. The parsed frame replaces
        the cached CSV frame, so the entire Compliance pipeline (run_analysis,
        snapshots, recalc, reports) is reused unchanged.
        """
        import core.analysis as ca
        from desktop.xls_host import load_winscope_df

        params = params or {}
        b64 = params.get("b64")
        if b64 is None:
            raise ValueError("load_winscope requires b64")

        self._df = load_winscope_df(b64, params.get("filename"))
        self._df_run = self._df_proc = self._df_events = self._config = None
        ok, errors, warnings = ca.validate_csv_format(self._df)
        t_min, t_max = self._time_range()
        return {
            "filename": params.get("filename"),
            "logger_format": self._df.attrs.get("logger_format"),
            "n_rows": int(len(self._df)),
            "columns": [str(c) for c in self._df.columns],
            "time_min": t_min,
            "time_max": t_max,
            "valid": bool(ok),
            "errors": errors,
            "warnings": warnings,
        }

    def _time_range(self) -> tuple:
        """(min, max) Timestamp of the loaded frame as ISO strings, or (None, None)."""
        import pandas as pd

        if self._df is None or self._df.empty or "Timestamp" not in self._df.columns:
            return None, None
        ts = pd.to_datetime(self._df["Timestamp"], errors="coerce").dropna()
        if ts.empty:
            return None, None
        return ts.min().isoformat(), ts.max().isoformat()

    # ---- Set Point comparison + ECU recordings ---------------------------
    @_logged
    def compare_setpoint(self, params: dict | None = None) -> dict:
        """Diff 2+ ECU parameter files (XLS/XLSX or ComAp CSV)."""
        from desktop.xls_host import compare_setpoint
        return compare_setpoint(params or {})

    @_logged
    def ecu_recording(self, params: dict | None = None) -> dict:
        """Read an ECU recording XLS/XLSX into grouped, JSON-safe time series."""
        from desktop.xls_host import load_ecu_recording_data
        return load_ecu_recording_data(params or {})

    # ---- analysis ---------------------------------------------------------
    @_logged
    def run_analysis(self, config: dict | None = None) -> dict:
        """Run the engine on the loaded CSV and return the JSON contract.

        ``config`` may carry ``time_start`` / ``time_end`` (ISO datetimes) to
        restrict the analysis to a sub-window of the loaded file; either may be
        null/absent for an open edge. These are not ``AnalysisConfig`` fields —
        they filter the frame before analysis and are ignored by ``_build_config``.
        """
        import core.analysis as ca
        from core.serialize import analysis_result
        from core.viz_dataprep import detected_events_overlay, itic_curve

        if self._df is None:
            raise RuntimeError("run_analysis called before load_csv")

        config = config or {}
        # Restrict to the selected time window (full file kept in self._df so a
        # later run with a different window doesn't need a re-upload).
        self._df_run = ca.filter_time_window(
            self._df, config.get("time_start"), config.get("time_end"))
        if self._df_run is None or self._df_run.empty:
            raise RuntimeError("Selected time window contains no data.")

        cfg = self._build_config(config)
        # Miro and WinScope sources skip the 100 ms interpolation (high-rate or
        # vendor-gridded data; see CLAUDE.md / ROADMAP).
        if self._df.attrs.get("logger_format") in ("miro", "winscope"):
            cfg.skip_interpolation = True

        self._df_proc, self._df_events = ca.perform_analysis(self._df_run, cfg)
        self._df_events = self._df_events.reset_index(drop=True)  # positional == label for snapshot/recalc
        self._config = cfg
        usage_log.record_analysis_run()
        result = analysis_result(self._df_proc, self._df_events,
                                 logger_format=self._df.attrs.get("logger_format"))
        result["itic"] = itic_curve(self._df_events, cfg.nominal_voltage)
        result["events_overlay"] = detected_events_overlay(self._df_events)
        return result

    @_logged
    def metric_series(self, column: str) -> dict:
        """Return one processed-metric time-series for charting."""
        from core.serialize import metric_series

        if self._df_proc is None:
            raise RuntimeError("metric_series called before run_analysis")
        return metric_series(self._df_proc, column)

    # ---- event snapshots --------------------------------------------------
    @_logged
    def snapshot(self, params: dict | None = None) -> dict:
        """Return the 4-panel snapshot data for one event (by positional index)."""
        from core.viz_dataprep import snapshot_data

        if self._df_proc is None or self._df_events is None:
            raise RuntimeError("snapshot called before run_analysis")
        params = params or {}
        pos = int(params.get("index", 0))
        n = len(self._df_events)
        if pos < 0 or pos >= n:
            raise IndexError(f"event index {pos} out of range (0..{n - 1})")
        prev_ts = self._df_events.iloc[pos - 1].get("Timestamp") if pos > 0 else None
        next_ts = self._df_events.iloc[pos + 1].get("Timestamp") if pos + 1 < n else None
        window_s = params.get("window_s")
        return snapshot_data(
            self._df_proc, self._df_events.iloc[pos], self._config,
            window_s=float(window_s) if window_s else None,
            time_offset_s=float(params.get("time_offset_s", 0.0) or 0.0),
            prev_event_ts=prev_ts, next_event_ts=next_ts, event_index=pos,
        )

    # ---- reports ----------------------------------------------------------
    def default_html_template(self) -> dict:
        """The built-in editable HTML report template, for the report editor."""
        from desktop.report_host import default_html_template
        return {"template": default_html_template()}

    @_logged
    def generate_report(self, params: dict | None = None) -> dict:
        """Build report artifacts (PDF/HTML/.docx) from the last analysis.

        Reports are produced host-side from the cached engine results (which
        already reflect any Recalculate overrides), so the report numbers match
        what the engine computed — never re-derived in JS.
        """
        from desktop.report_host import build_report

        if self._df is None or self._df_proc is None or self._df_events is None:
            raise RuntimeError("generate_report called before run_analysis")
        # Use the windowed frame the analysis ran on so report snapshots match.
        df_raw = self._df_run if self._df_run is not None else self._df
        result = build_report(df_raw, self._df_proc, self._df_events, self._config,
                              params or {})
        usage_log.record_report_generated()
        return result

    def save_dialog(self, params: dict | None = None) -> dict:
        """Write base64 ``data_b64`` to a path chosen via the native Save dialog.

        Returns ``{"path": <str>}`` on success, ``{"path": None}`` if the user
        cancelled, or ``{"path": None, "error": ...}`` if no window is available
        (e.g. unit tests, where ``webview`` is not running). Browser-style blob
        downloads remain the cross-platform fallback in the frontend.
        """
        params = params or {}
        data_b64 = params.get("data_b64")
        if data_b64 is None:
            raise ValueError("save_dialog requires data_b64")
        filename = params.get("filename") or "PQA_Report.pdf"
        try:
            import webview
            windows = getattr(webview, "windows", None) or []
            if not windows:
                return {"path": None, "error": "no active window"}
            chosen = windows[0].create_file_dialog(
                webview.SAVE_DIALOG, save_filename=filename)
            path = chosen[0] if isinstance(chosen, (list, tuple)) else chosen
            if not path:
                return {"path": None}
            with open(path, "wb") as f:
                f.write(base64.b64decode(data_b64))
            return {"path": str(path)}
        except Exception as exc:  # noqa: BLE001 — never crash the bridge
            return {"path": None, "error": str(exc)}

    # ---- per-event overrides + recalculate --------------------------------
    @_logged
    def recalc(self, params: dict | None = None) -> dict:
        """Apply per-event overrides and re-run compliance; return updated events."""
        from core.recalc import apply_overrides, recompute_df_interp
        from core.serialize import events_to_records
        from core.viz_dataprep import itic_curve

        if self._df_proc is None or self._df_events is None:
            raise RuntimeError("recalc called before run_analysis")
        overrides = (params or {}).get("overrides", {})
        df_interp = recompute_df_interp(
            self._df_proc, getattr(self._config, "skip_interpolation", False))
        self._df_events = apply_overrides(self._df_events, df_interp, self._config, overrides)
        return {
            "events": events_to_records(self._df_events),
            "itic": itic_curve(self._df_events, self._config.nominal_voltage),
        }

    # ---- helpers ----------------------------------------------------------
    def _build_config(self, config: dict | None):
        import core.analysis as ca

        cfg = ca.AnalysisConfig()
        if config:
            valid = {f.name for f in dataclasses.fields(cfg)}
            for key, value in config.items():
                if key in valid and value is not None:
                    setattr(cfg, key, value)
        return cfg


def _index_url() -> str:
    """Local path to the built web UI, or a placeholder if it isn't built yet.

    Works from source and when frozen by PyInstaller (onedir/onefile), where the
    bundled web assets live under ``sys._MEIPASS``. The UI is a single
    self-contained HTML file, so it loads from ``file://`` with no web server.
    """
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        built = os.path.join(base, "web", "dist", "index.html")
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        built = os.path.join(here, os.pardir, "web", "dist", "index.html")
    if os.path.exists(built):
        return built
    return ("data:text/html,<h1 style='font-family:sans-serif'>PQA desktop shell</h1>"
            "<p>Build the web UI first: <code>cd web &amp;&amp; npm install &amp;&amp; npm run build</code></p>")


def main() -> None:
    """Launch the desktop window (Windows: WebView2 / Edge Chromium)."""
    # On Windows (including ARM64 under Parallels), pythonnet must use the
    # built-in .NET Framework 4.8.1 (which includes WinForms) rather than
    # trying to load coreclr. Set before any pywebview/pythonnet import.
    if sys.platform == "win32":
        os.environ.setdefault("PYTHONNET_RUNTIME", "netfx")

    # Record uncaught exceptions (main thread + worker threads) to the local
    # crash log before the app goes down, so failures leave an inspectable trail.
    usage_log.install_global_handlers()

    import webview  # lazy: only needed to actually open a window

    bridge = HostBridge()
    window = webview.create_window("PQA PROJECT", url=_index_url(),
                                   js_api=bridge, width=1400, height=900, min_size=(1024, 700))

    # Track time spent in the app: start the timer when the window is shown and
    # flush the remaining interval when it closes. Logging is best-effort and
    # never blocks window lifecycle.
    timer = usage_log.SessionTimer()
    timer.start()
    try:
        window.events.closing += timer.stop
    except Exception:  # noqa: BLE001 — event API differences must not break launch
        pass

    # gui='edgechromium' forces WebView2 on Windows; harmless elsewhere.
    webview.start(gui="edgechromium")
    timer.stop()  # belt-and-braces final flush after the event loop exits


if __name__ == "__main__":
    main()
