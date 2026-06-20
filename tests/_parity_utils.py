"""Helpers to serialise analysis output into a stable, comparable form.

The parity tests assert that the engine in ``core.analysis`` reproduces a frozen
"golden" result on fixed inputs — protecting the migration (and, later, the
Pyodide/iPad path) against accidental numeric drift.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Columns whose summary stats stand in for the (large) processed frame.
PROC_STAT_COLS = ("Avg_Voltage_LL", "Avg_Frequency", "Avg_kW", "Avg_Current", "Avg_PF")

# Rounding applied to floats before storage so golden files are stable across runs.
_FLOAT_NDIGITS = 9


def canonical_events(df: pd.DataFrame) -> list[dict]:
    """Return ``df_events`` as a row-major list of JSON-safe dicts.

    Done column-wise (not via ``iterrows``) so per-column dtypes are preserved
    instead of being upcast into a common row dtype.
    """
    cols: dict[str, list] = {}
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            cols[col] = [None if pd.isna(x) else pd.Timestamp(x).isoformat() for x in s]
        elif pd.api.types.is_bool_dtype(s):
            cols[col] = [bool(x) for x in s]
        elif pd.api.types.is_integer_dtype(s):
            cols[col] = [int(x) for x in s]
        elif pd.api.types.is_float_dtype(s):
            cols[col] = [None if pd.isna(x) else round(float(x), _FLOAT_NDIGITS) for x in s]
        else:  # object / string (may contain NaN)
            out = []
            for x in s:
                if x is None:
                    out.append(None)
                elif isinstance(x, float) and math.isnan(x):
                    out.append(None)
                else:
                    out.append(str(x))
            cols[col] = out
    n = len(df)
    return [{c: cols[c][i] for c in df.columns} for i in range(n)]


def proc_signature(df: pd.DataFrame, stat_cols=PROC_STAT_COLS) -> dict:
    """Compact signature of the processed frame: shape + per-column summary stats."""
    sig: dict = {"n_rows": int(len(df)), "columns": [str(c) for c in df.columns]}
    stats: dict[str, dict] = {}
    for c in stat_cols:
        if c in df.columns:
            vals = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype="float64")
            has = np.isfinite(vals).any()
            stats[c] = {
                "sum": round(float(np.nansum(vals)), 6),
                "mean": round(float(np.nanmean(vals)), 6) if has else None,
                "min": round(float(np.nanmin(vals)), 6) if has else None,
                "max": round(float(np.nanmax(vals)), 6) if has else None,
            }
    sig["stats"] = stats
    return sig


def deep_diff(golden, current, atol: float = 1e-6, path: str = "", out: list | None = None) -> list[str]:
    """Recursively diff two JSON-like structures; floats compared with ``atol``."""
    if out is None:
        out = []
    if isinstance(golden, dict) and isinstance(current, dict):
        for k in sorted(set(golden) | set(current)):
            if k not in current:
                out.append(f"{path}.{k}: missing in current")
            elif k not in golden:
                out.append(f"{path}.{k}: unexpected in current")
            else:
                deep_diff(golden[k], current[k], atol, f"{path}.{k}", out)
    elif isinstance(golden, list) and isinstance(current, list):
        if len(golden) != len(current):
            out.append(f"{path}: length {len(golden)} (golden) != {len(current)} (current)")
        else:
            for i, (g, c) in enumerate(zip(golden, current)):
                deep_diff(g, c, atol, f"{path}[{i}]", out)
    elif (
        isinstance(golden, (int, float)) and isinstance(current, (int, float))
        and not isinstance(golden, bool) and not isinstance(current, bool)
    ):
        if not math.isclose(float(golden), float(current), rel_tol=0.0, abs_tol=atol):
            out.append(f"{path}: {golden} != {current} (atol={atol})")
    else:
        if golden != current:
            out.append(f"{path}: {golden!r} != {current!r}")
    return out
