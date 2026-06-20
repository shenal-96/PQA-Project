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
import io
import os
import sys


class HostBridge:
    """Methods here are exposed to JS as ``window.pywebview.api.<name>(...)``.

    Only JSON-serialisable args/returns cross the bridge. The last loaded frame
    and analysis result are cached so follow-up calls (charts, recalculation,
    reports) reuse them.
    """

    def __init__(self) -> None:
        self._df = None          # raw loaded frame
        self._df_proc = None     # processed frame
        self._df_events = None   # detected events
        self._config = None      # AnalysisConfig used for the last run

    # ---- capabilities -----------------------------------------------------
    def caps(self) -> dict:
        """Platform capability flags the frontend gates features on."""
        return {"platform": "desktop", "canReport": True, "canXls": True}

    # ---- CSV ingest -------------------------------------------------------
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
        self._df_proc = self._df_events = self._config = None
        ok, errors, warnings = ca.validate_csv_format(self._df)
        return {
            "filename": filename,
            "logger_format": self._df.attrs.get("logger_format"),
            "n_rows": int(len(self._df)),
            "columns": [str(c) for c in self._df.columns],
            "valid": bool(ok),
            "errors": errors,
            "warnings": warnings,
        }

    # ---- analysis ---------------------------------------------------------
    def run_analysis(self, config: dict | None = None) -> dict:
        """Run the engine on the loaded CSV and return the JSON contract."""
        import core.analysis as ca
        from core.serialize import analysis_result

        if self._df is None:
            raise RuntimeError("run_analysis called before load_csv")

        cfg = self._build_config(config)
        # Miro logger never uses the 100 ms interpolation (see CLAUDE.md).
        if self._df.attrs.get("logger_format") == "miro":
            cfg.skip_interpolation = True

        self._df_proc, self._df_events = ca.perform_analysis(self._df, cfg)
        self._df_events = self._df_events.reset_index(drop=True)  # positional == label for snapshot/recalc
        self._config = cfg
        return analysis_result(self._df_proc, self._df_events,
                               logger_format=self._df.attrs.get("logger_format"))

    def metric_series(self, column: str) -> dict:
        """Return one processed-metric time-series for charting."""
        from core.serialize import metric_series

        if self._df_proc is None:
            raise RuntimeError("metric_series called before run_analysis")
        return metric_series(self._df_proc, column)

    # ---- event snapshots --------------------------------------------------
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

    # ---- per-event overrides + recalculate --------------------------------
    def recalc(self, params: dict | None = None) -> dict:
        """Apply per-event overrides and re-run compliance; return updated events."""
        from core.recalc import apply_overrides, recompute_df_interp
        from core.serialize import events_to_records

        if self._df_proc is None or self._df_events is None:
            raise RuntimeError("recalc called before run_analysis")
        overrides = (params or {}).get("overrides", {})
        df_interp = recompute_df_interp(
            self._df_proc, getattr(self._config, "skip_interpolation", False))
        self._df_events = apply_overrides(self._df_events, df_interp, self._config, overrides)
        return {"events": events_to_records(self._df_events)}

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

    import webview  # lazy: only needed to actually open a window

    bridge = HostBridge()
    webview.create_window("PQA — Power Quality Analysis", url=_index_url(),
                          js_api=bridge, width=1400, height=900, min_size=(1024, 700))
    # gui='edgechromium' forces WebView2 on Windows; harmless elsewhere.
    webview.start(gui="edgechromium")


if __name__ == "__main__":
    main()
