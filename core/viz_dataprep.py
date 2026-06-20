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

import pandas as pd

from core.serialize import _cell


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
