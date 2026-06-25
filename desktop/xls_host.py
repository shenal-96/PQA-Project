"""Host-side XLS/XLSX ingestion for the WinScope, Set Point and ECU tabs.

Everything here is desktop-only (the future iPad/PWA path is Compliance-CSV
only). XLS/XLSX is read with **python_calamine** — robust against the vendor
exports xlrd chokes on — either directly (WinScope / ECU recordings) or via
pandas' ``engine="calamine"`` (Set Point parameter files through ``ecu_parser``).

The heavy parsers (``core.analysis``, ``ecu_*``) are imported lazily so this
module stays cheap to import in the lean CI pytest job. Files cross the
PyWebview bridge as base64; each helper writes a temp file (calamine reads
paths), parses, and cleans up.
"""
from __future__ import annotations

import base64
import os
import tempfile


def _write_temp(b64: str, suffix: str) -> str:
    """Decode base64 ``b64`` to a temp file with ``suffix`` and return its path."""
    raw = base64.b64decode(b64)
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
    return path


def _ext_for(name: str | None, default: str) -> str:
    ext = os.path.splitext(name or "")[1].lower()
    return ext if ext in (".xls", ".xlsx", ".csv") else default


# ── WinScope ────────────────────────────────────────────────────────────────────

def load_winscope_df(b64: str, filename: str | None = None):
    """Read a WinScope .xls/.xlsx export into a perform_analysis-ready frame.

    Tags ``df.attrs["logger_format"] = "winscope"`` so the bridge runs the engine
    with ``skip_interpolation=True`` (high-rate source; see ROADMAP / CLAUDE.md).
    """
    import core.analysis as ca

    path = _write_temp(b64, _ext_for(filename, ".xls"))
    try:
        df = ca.load_winscope_xls(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    df.attrs["logger_format"] = "winscope"
    return df


# ── Set Point comparison ────────────────────────────────────────────────────────

def compare_setpoint(params: dict) -> dict:
    """Diff 2+ ECU parameter files and return a JSON-safe table of differences.

    ``params``: ``{"kind": "xls"|"csv", "files": [{"filename", "b64"}, ...]}``.
    Reuses ``ecu_parser``/``ecu_multi_comparator`` (XLS, calamine engine) or
    ``ecu_csv_parser``/``ecu_csv_comparator`` (ComAp CSV). Returns columns (the
    fixed identity columns followed by one column per file label), the per-file
    labels, and one row per differing location.
    """
    from core.serialize import _cell

    kind = (params or {}).get("kind", "xls")
    files_in = (params or {}).get("files") or []
    if len(files_in) < 2:
        raise ValueError("Select at least two files to compare.")

    opts = (params or {}).get("options") or {}
    hide_unchanged = bool(opts.get("hide_unchanged", False))
    ignore_whitespace = bool(opts.get("ignore_whitespace", False))
    ignore_case = bool(opts.get("ignore_case", False))

    parsed: dict = {}
    tmps: list[str] = []
    try:
        for meta in files_in:
            name = meta.get("filename") or "file"
            if kind == "csv":
                import ecu_csv_parser
                path = _write_temp(meta["b64"], ".csv")
                tmps.append(path)
                result = ecu_csv_parser.parse_csv_file(path)
            else:
                import ecu_parser
                path = _write_temp(meta["b64"], _ext_for(name, ".xlsx"))
                tmps.append(path)
                result = ecu_parser.parse_file(path, engine="calamine")

            # Unique, human-readable label per file (filename stem).
            base = os.path.splitext(name)[0] or "file"
            label, n = base, 2
            while label in parsed:
                label, n = f"{base} ({n})", n + 1
            parsed[label] = result

        if kind == "csv":
            import ecu_csv_comparator
            diffs = ecu_csv_comparator.compare_csv_files(parsed)
            fixed = ["Group", "Sub-group", "Name", "Dimension"]
        else:
            import ecu_multi_comparator
            diffs = ecu_multi_comparator.compare_all_files(parsed)
            fixed = ["Sheet", "Nr", "Name", "Location"]
    finally:
        for path in tmps:
            try:
                os.unlink(path)
            except OSError:
                pass

    labels = list(parsed.keys())
    columns = fixed + labels
    rows = [{col: _cell(row.get(col)) for col in columns} for row in diffs]
    result = {
        "kind": kind,
        "columns": columns,
        "labels": labels,
        "rows": rows,
        "n_files": len(labels),
        "n_diffs": len(rows),
    }

    # Also build the Diffchecker-style side-by-side HTML view from the same
    # already-parsed file data (``parsed`` is ``{label: parse_result}`` — exactly
    # the shape ``build_csv_view``/``build_xls_view`` expect). Never let a view
    # failure break the flat-table contract: on any error, omit ``html``.
    try:
        import comparison_view

        if kind == "csv":
            html, _ = comparison_view.build_csv_view(
                parsed,
                hide_unchanged=hide_unchanged,
                ignore_whitespace=ignore_whitespace,
                ignore_case=ignore_case,
            )
        else:
            html, _ = comparison_view.build_xls_view(
                parsed,
                hide_unchanged=hide_unchanged,
                ignore_whitespace=ignore_whitespace,
                ignore_case=ignore_case,
            )
        result["html"] = html
    except Exception:
        pass

    return result


# ── ECU recording (time-series) ─────────────────────────────────────────────────

def load_ecu_recording_data(params: dict) -> dict:
    """Read an ECU recording XLS/XLSX into JSON-safe series + channel grouping.

    ``params``: ``{"filename": str, "b64": str}``. Returns aligned ``timestamps``,
    a ``channels`` map (raw name → values), the keyword-based ``groups`` mapping,
    and humanised ``labels`` for each raw channel name.
    """
    import pandas as pd

    from core.serialize import _cell
    from ecu_recording_parser import (
        classify_columns, load_ecu_recording, _tidy_channel_label,
    )

    name = (params or {}).get("filename") or "recording.xls"
    path = _write_temp(params["b64"], _ext_for(name, ".xls"))
    try:
        df = load_ecu_recording(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    channels = [c for c in df.columns if c != "Timestamp"]
    series = {
        c: [None if pd.isna(v) else float(v)
            for v in pd.to_numeric(df[c], errors="coerce")]
        for c in channels
    }
    return {
        "filename": name,
        "n_rows": int(len(df)),
        "timestamps": [_cell(t) for t in df["Timestamp"]],
        "channels": series,
        "groups": classify_columns(channels),
        "labels": {c: _tidy_channel_label(c) for c in channels},
    }
