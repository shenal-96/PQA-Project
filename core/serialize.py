"""JSON data contract shared by every backend.

This is the single definition of how analysis results cross the
frontend<->backend boundary. The Windows ``HostBridge`` (PyWebview) returns
exactly these shapes today; the future iPad ``PyodideBackend`` will return the
**identical** shapes, so the UI never needs to know which backend it is talking
to. Everything here is JSON-serialisable (no pandas/numpy types leak out).
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

# Metric columns surfaced to the on-screen charts, in display order.
DEFAULT_METRICS = (
    "Avg_kW",
    "Avg_Voltage_LL",
    "Avg_Current",
    "Avg_Frequency",
    "Avg_PF",
    "Avg_THD_F",
)


def _cell(value: Any) -> Any:
    """Convert a single pandas/numpy cell to a JSON-safe Python value."""
    if value is None:
        return None
    # NaT / NaN (scalar) -> None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalar -> python scalar
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def events_to_records(df_events: pd.DataFrame) -> list[dict]:
    """``df_events`` as a row-major list of JSON-safe dicts (full precision)."""
    cols: dict[str, list] = {col: [_cell(v) for v in df_events[col]] for col in df_events.columns}
    n = len(df_events)
    return [{col: cols[col][i] for col in df_events.columns} for i in range(n)]


def metric_series(df_proc: pd.DataFrame, column: str, time_col: str = "Timestamp") -> dict:
    """A single time-series for ECharts: aligned timestamp + value arrays."""
    if column not in df_proc.columns:
        return {"column": column, "timestamps": [], "values": []}
    ts = df_proc[time_col] if time_col in df_proc.columns else pd.Series(range(len(df_proc)))
    vals = pd.to_numeric(df_proc[column], errors="coerce")
    return {
        "column": column,
        "timestamps": [_cell(t) for t in ts],
        "values": [None if pd.isna(v) else float(v) for v in vals],
    }


def analysis_result(df_proc: pd.DataFrame, df_events: pd.DataFrame, metrics=DEFAULT_METRICS) -> dict:
    """The full payload returned by ``HostBridge.run_analysis`` (and Pyodide later)."""
    return {
        "logger_format": df_proc.attrs.get("logger_format"),
        "n_rows": int(len(df_proc)),
        "events": events_to_records(df_events),
        "metrics": {m: metric_series(df_proc, m) for m in metrics if m in df_proc.columns},
    }
