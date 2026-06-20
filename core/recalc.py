"""Per-event override + recalculate-compliance logic (pure, host + future Pyodide).

Ported from the legacy Streamlit ``_recompute_df_interp`` / Recalculate flow
(app.py). Reuses the engine functions ``calculate_recovery_time`` and
``check_compliance`` unchanged so recalculated numbers match the original run.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.analysis import calculate_recovery_time, check_compliance

# Default per-event override shape (matches app.py intersection_overrides).
_DEFAULT_OVERRIDE = {
    "v_exit_offset": 0.0,
    "v_rec_override": None,
    "f_exit_offset": 0.0,
    "f_rec_override": None,
}


def recompute_df_interp(df_proc: pd.DataFrame, skip_interpolation: bool = False) -> pd.DataFrame:
    """Re-derive the 100 ms interpolated frame for exact crossing detection.

    Mirrors app.py ``_recompute_df_interp`` and ``perform_analysis`` (analysis.py
    ~779-791). Returns ``df_proc.copy()`` unchanged when interpolation is skipped
    (Miro / WinScope high-rate sources).
    """
    if skip_interpolation:
        return df_proc.copy()
    num_cols = df_proc.select_dtypes(include=[np.number]).columns
    return (
        df_proc.set_index("Timestamp")[num_cols]
        .resample("100ms")
        .mean()
        .interpolate(method="linear")
        .reset_index()
    )


def apply_overrides(df_events: pd.DataFrame, df_interp: pd.DataFrame, config, overrides: dict) -> pd.DataFrame:
    """Apply per-event exit/recovery overrides and re-run compliance.

    ``overrides`` maps event **position** (int or str) -> a dict with
    ``v_exit_offset, v_rec_override, f_exit_offset, f_rec_override``. Returns a new
    df_events with adjusted ``V/F_exit_ts``, ``V/F_rec_s`` and refreshed compliance
    columns. Voltage recovery uses the symmetric tolerance band; frequency uses the
    direction-dependent recovery band (matches app.py 586-634).
    """
    df_ev = df_events.reset_index(drop=True).copy()
    v_upper = config.nominal_voltage * (1 + config.voltage_tolerance_pct / 100)
    v_lower = config.nominal_voltage * (1 - config.voltage_tolerance_pct / 100)

    for pos_key, raw_ov in (overrides or {}).items():
        pos = int(pos_key)
        if pos < 0 or pos >= len(df_ev):
            continue
        ov = {**_DEFAULT_OVERRIDE, **(raw_ov or {})}
        row = df_ev.iloc[pos]
        dkw = row.get("dKw", 0) or 0

        # -- Voltage -----------------------------------------------------------
        v_exit_orig = row.get("V_exit_ts")
        v_exit_adj = (
            pd.Timestamp(v_exit_orig) + pd.Timedelta(seconds=ov["v_exit_offset"])
            if pd.notnull(v_exit_orig) else None
        )
        if v_exit_adj is not None:
            df_ev.at[pos, "V_exit_ts"] = v_exit_adj
        if ov["v_rec_override"] is not None:
            new_v_rec = ov["v_rec_override"]
        elif v_exit_adj is not None and ov["v_exit_offset"] != 0.0:
            new_v_rec = calculate_recovery_time(df_interp, v_exit_adj, "Avg_Voltage_LL", v_upper, v_lower)
        else:
            new_v_rec = row.get("V_rec_s")
        df_ev.at[pos, "V_rec_s"] = new_v_rec

        # -- Frequency ---------------------------------------------------------
        f_exit_orig = row.get("F_exit_ts")
        f_exit_adj = (
            pd.Timestamp(f_exit_orig) + pd.Timedelta(seconds=ov["f_exit_offset"])
            if pd.notnull(f_exit_orig) else None
        )
        if f_exit_adj is not None:
            df_ev.at[pos, "F_exit_ts"] = f_exit_adj
        f_upper = config.freq_recovery_upper_increase if dkw > 0 else config.freq_recovery_upper_decrease
        f_lower = config.freq_recovery_lower_increase if dkw > 0 else config.freq_recovery_lower_decrease
        if ov["f_rec_override"] is not None:
            new_f_rec = ov["f_rec_override"]
        elif f_exit_adj is not None and ov["f_exit_offset"] != 0.0:
            new_f_rec = calculate_recovery_time(df_interp, f_exit_adj, "Avg_Frequency", f_upper, f_lower)
        else:
            new_f_rec = row.get("F_rec_s")
        df_ev.at[pos, "F_rec_s"] = new_f_rec

        # -- Re-run compliance (writes all four fields) ------------------------
        comp = check_compliance(df_ev.iloc[pos], config)
        for field in ("Compliance_Status", "Failure_Reasons", "Potential_Fault", "Fault_Reasons"):
            df_ev.at[pos, field] = comp[field]

    return df_ev
