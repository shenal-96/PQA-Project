"""Pure chart data-prep shared by the on-screen ECharts UI and (later) the
matplotlib report images.

This is the single source of truth for *what* a chart shows (series, markers,
bands) — independent of *how* it is drawn. **No matplotlib import here**; the
host report renderer will consume these same structures so screen and report
stay consistent.

Only a first slice is implemented (the Detected-Events overlay used by the kW
time-series). The snapshot window/marker math from ``visualizations.py``
(``plot_load_change_snapshot``) lands here as the Compliance UI is built.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.serialize import _cell

# Snapshot plots are resampled to a fixed rate so the line has a consistent
# density regardless of the logger's native sample rate.
SNAPSHOT_PLOT_HZ = 5
SNAPSHOT_PLOT_PERIOD = f"{int(1000 / SNAPSHOT_PLOT_HZ)}ms"  # 200ms = 5 points/second


def detected_events_overlay(df_events: pd.DataFrame) -> list[dict]:
    """Vertical-line markers for the kW 'Detected Events' time-series overlay.

    Returns one entry per event: its timestamp, signed load step, and a label
    like ``"+220 kW"`` / ``"-160 kW"``.
    """
    out: list[dict] = []
    ts_col = "Start_Timestamp" if "Start_Timestamp" in df_events.columns else "Timestamp"
    for _, row in df_events.iterrows():
        dkw = row.get("dKw")
        has_dkw = dkw is not None and not pd.isna(dkw)
        out.append({
            "timestamp": _cell(row.get(ts_col)),
            "dKw": float(dkw) if has_dkw else None,
            "label": (f"{'+' if dkw >= 0 else ''}{int(round(dkw))} kW") if has_dkw else "",
        })
    return out


# --- Per-event snapshot data (4-panel V/I/F/kW) ---------------------------------
# Pure port of the window math + asymmetric band/limit/marker logic from
# visualizations.py:plot_load_change_snapshot. On-screen snapshots use the
# df_proc averaged columns (one line per panel), not the legacy 3-phase raw series.

# (column, label, colour) per panel.
_SNAPSHOT_PANELS = {
    "voltage": ("Avg_Voltage_LL", "Voltage L-L (V)", "#9333ea"),
    "current": ("Avg_Current", "Current (A)", "#0891b2"),
    "frequency": ("Avg_Frequency", "Frequency (Hz)", "#16a34a"),
    "power": ("Avg_kW", "Active Power (kW)", "#2563eb"),
}


def _iso(ts):
    return None if ts is None or pd.isna(ts) else pd.Timestamp(ts).isoformat()


def _num(x):
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    return float(x)


def _resample_plot(win):
    """Resample a snapshot window to SNAPSHOT_PLOT_HZ (5 points/second).

    Bins the numeric columns onto a fixed 200 ms grid and linearly interpolates
    (filling the leading/trailing edges) so the snapshot line is drawn at a
    consistent density whatever the logger's native rate. Purely cosmetic — the
    compliance numbers come from analysis, never from this resampled frame.
    """
    if win is None or win.empty or "Timestamp" not in win.columns:
        return win
    num = list(win.select_dtypes(include="number").columns)
    if not num:
        return win
    out = (
        win.set_index("Timestamp")[num]
        .resample(SNAPSHOT_PLOT_PERIOD).mean()
        .interpolate(method="linear", limit_direction="both")
        .reset_index()
    )
    return out


def _panel(win, col, label, color) -> dict:
    if col in win.columns:
        timestamps = [_iso(t) for t in win["Timestamp"]]
        values = [None if pd.isna(v) else float(v) for v in pd.to_numeric(win[col], errors="coerce")]
    else:
        timestamps, values = [], []
    return {"label": label, "color": color, "column": col,
            "timestamps": timestamps, "values": values}


def _decorate(panel, get, direction, nom, maxdev_default, win, col, prefix) -> None:
    """Add band / direction-relevant limit / exit+recovery+extreme markers to a panel."""
    upper = _num(get(f"{prefix}_rec_upper"))
    lower = _num(get(f"{prefix}_rec_lower"))
    if upper is not None and lower is not None:
        panel["band"] = {"upper": upper, "lower": lower}

    # Direction-relevant max-deviation limit (increase -> lower; decrease -> upper).
    if direction == "increase":
        pct = _num(get(f"{prefix}_max_dev_lower_pct"))
        pct = pct if pct is not None else maxdev_default
        panel["limit"] = {"value": nom * (1 - pct / 100.0), "side": "lower", "pct": pct}
    else:
        pct = _num(get(f"{prefix}_max_dev_upper_pct"))
        pct = pct if pct is not None else maxdev_default
        panel["limit"] = {"value": nom * (1 + pct / 100.0), "side": "upper", "pct": pct}

    dev = _num(get(f"{prefix}_dev"))
    ex = get(f"{prefix}_exit_ts")
    rc = _num(get(f"{prefix}_rec_s"))
    band_val = upper if (dev is not None and dev > nom) else lower
    if ex is not None and pd.notnull(ex):
        panel["exit"] = {"ts": _iso(ex), "value": band_val}
        if rc is not None:
            panel["recovery"] = {
                "ts": _iso(pd.Timestamp(ex) + pd.Timedelta(seconds=rc)),
                "value": band_val, "rec_s": rc,
            }
    if dev is not None and col in win.columns and len(win):
        series = pd.to_numeric(win[col], errors="coerce")
        if series.notna().any():
            idx = series.idxmin() if direction == "increase" else series.idxmax()
            panel["extreme"] = {"ts": _iso(win.loc[idx, "Timestamp"]), "value": dev}
    nr = get(f"{prefix}_not_recovered")
    panel["not_recovered"] = bool(nr) if (nr is not None and pd.notnull(nr)) else False


def snapshot_data(df_proc, event_row, config, window_s=None, time_offset_s=0.0,
                  prev_event_ts=None, next_event_ts=None, event_index=None) -> dict:
    """JSON-serialisable 4-panel snapshot for one event.

    Mirrors visualizations.py:plot_load_change_snapshot window logic (lines 609-652):
    symmetric window of ``window_s`` shifted by ``time_offset_s``, widened to include
    exit/recovery markers, and clamped to neighbour events unless the user has
    deliberately shifted the window.
    """
    get = event_row.get
    event_ts = pd.Timestamp(get("Timestamp"))
    if window_s is None:
        window_s = float(getattr(config, "snapshot_window_s", 10.0))
    window_s = float(window_s)
    time_offset_s = float(time_offset_s or 0.0)

    half = window_s / 2.0
    left_s = max(0.5, half - time_offset_s)
    right_s = max(0.5, half + time_offset_s)

    # Widen to include exit / recovery markers (+2 s buffer).
    for exit_key, rec_key in (("V_exit_ts", "V_rec_s"), ("F_exit_ts", "F_rec_s")):
        ex = get(exit_key)
        rc = _num(get(rec_key))
        if ex is not None and pd.notnull(ex):
            left_s = max(left_s, (event_ts - pd.Timestamp(ex)).total_seconds() + 2)
            if rc is not None:
                marker_ts = pd.Timestamp(ex) + pd.Timedelta(seconds=rc)
                right_s = max(right_s, (marker_ts - event_ts).total_seconds() + 2)

    # Neighbour clamp — skipped on deliberate shift.
    explicit = abs(time_offset_s) > 1e-9
    if not explicit and next_event_ts is not None and pd.notnull(next_event_ts):
        mr = (pd.Timestamp(next_event_ts) - event_ts).total_seconds()
        if mr > 0:
            right_s = min(right_s, mr)
    if not explicit and prev_event_ts is not None and pd.notnull(prev_event_ts):
        ml = (event_ts - pd.Timestamp(prev_event_ts)).total_seconds()
        if ml > 0:
            left_s = min(left_s, ml)

    lo = event_ts - pd.Timedelta(seconds=left_s)
    hi = event_ts + pd.Timedelta(seconds=right_s)
    win = df_proc[(df_proc["Timestamp"] >= lo) & (df_proc["Timestamp"] <= hi)]
    win = _resample_plot(win)  # 5 data points/second

    dkw = _num(get("dKw")) or 0.0
    direction = "increase" if dkw > 0 else "decrease"
    nom_v = float(config.nominal_voltage)
    nom_f = float(config.nominal_frequency)

    panels = {k: _panel(win, col, label, color) for k, (col, label, color) in _SNAPSHOT_PANELS.items()}
    _decorate(panels["voltage"], get, direction, nom_v,
              float(config.voltage_max_deviation_pct), win, "Avg_Voltage_LL", "V")
    _decorate(panels["frequency"], get, direction, nom_f,
              float(config.frequency_max_deviation_pct), win, "Avg_Frequency", "F")

    return {
        "event_index": event_index,
        "event_ts": _iso(event_ts),
        "window_s": window_s,
        "left_s": float(left_s),
        "right_s": float(right_s),
        "time_offset_s": time_offset_s,
        "dKw": dkw,
        "direction": direction,
        "panels": panels,
    }


# --- ITIC / CBEMA curve ---------------------------------------------------------
# Standard ITIC envelope (% of nominal voltage vs event duration in seconds).
# Each tuple = (start_s, end_s, percent); vertical steps are implicit at segment
# boundaries. Mirrors visualizations.plot_itic_curve (kept here as pure data so
# core stays matplotlib-free).
_ITIC_UPPER = [
    (1e-4, 1e-3, 500),
    (1e-3, 3e-3, 200),
    (3e-3, 0.5, 140),
    (0.5, 10, 120),
    (10, 1e3, 110),
]
_ITIC_LOWER = [
    (1e-4, 0.02, 0),
    (0.02, 0.5, 70),
    (0.5, 10, 80),
    (10, 1e3, 90),
]


def _itic_envelope_at(x_s, segments):
    for a, b, y in segments:
        if a <= x_s <= b:
            return y
    if x_s < segments[0][0]:
        return segments[0][2]
    return segments[-1][2]


def _itic_polyline(segments):
    """Stepped segment list -> [[x, y], ...] polyline (with vertical risers)."""
    out: list[list[float]] = []
    for i, (a, b, y) in enumerate(segments):
        out.append([float(a), float(y)])
        out.append([float(b), float(y)])
        if i + 1 < len(segments):
            out.append([float(b), float(segments[i + 1][2])])  # riser to next level
    return out


def itic_curve(df_events, nominal_voltage, x_min=1e-3, x_max=1e3, y_max=250.0) -> dict:
    """JSON-serialisable ITIC (CBEMA) curve: envelopes + classified event points.

    Each plottable event (one with V_exit_ts, V_rec_s and V_dev) becomes a point at
    ``(V_rec_s, V_dev / nominal * 100)`` flagged ``inside`` when it sits within the
    ITIC envelope. Matches visualizations.plot_itic_curve.
    """
    nom = float(nominal_voltage) if nominal_voltage else 415.0
    events: list[dict] = []
    if df_events is not None and not df_events.empty and \
            {"V_dev", "V_rec_s", "V_exit_ts"}.issubset(df_events.columns):
        mask = (df_events["V_exit_ts"].notna() & df_events["V_rec_s"].notna()
                & df_events["V_dev"].notna())
        for _, row in df_events.loc[mask].iterrows():
            dur = float(row["V_rec_s"])
            pct = float(row["V_dev"]) / nom * 100.0
            if dur <= 0 or not np.isfinite(dur) or not np.isfinite(pct):
                continue
            upper = _itic_envelope_at(dur, _ITIC_UPPER)
            lower = _itic_envelope_at(dur, _ITIC_LOWER)
            events.append({"dur": dur, "pct": pct, "inside": bool(lower <= pct <= upper)})
    return {
        "upper": _itic_polyline(_ITIC_UPPER),
        "lower": _itic_polyline(_ITIC_LOWER),
        "events": events,
        "x_min": float(x_min),
        "x_max": float(x_max),
        "y_max": float(y_max),
    }
