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
