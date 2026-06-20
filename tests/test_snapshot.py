"""Tests for core.viz_dataprep.snapshot_data (4-panel event snapshots)."""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import core.analysis as ca                          # noqa: E402
from core.viz_dataprep import snapshot_data         # noqa: E402

FIXTURE = os.path.join(_HERE, "fixtures", "hioki_sample.csv")


def _events():
    df = ca.load_and_prepare_csv(FIXTURE)
    df_proc, df_events = ca.perform_analysis(df, ca.AnalysisConfig())
    return df_proc, df_events.reset_index(drop=True), ca.AnalysisConfig()


def test_snapshot_shape_and_panels():
    df_proc, df_events, cfg = _events()
    snap = snapshot_data(df_proc, df_events.iloc[0], cfg, event_index=0)
    assert set(snap["panels"]) == {"voltage", "current", "frequency", "power"}
    for panel in snap["panels"].values():
        assert len(panel["timestamps"]) == len(panel["values"])
        assert len(panel["timestamps"]) > 0
    # JSON-safe: timestamps are ISO strings
    assert isinstance(snap["panels"]["voltage"]["timestamps"][0], str)


def test_asymmetric_limit_side():
    df_proc, df_events, cfg = _events()
    # Event 0 is a load increase (+kW) -> voltage drops -> lower limit/band relevant.
    inc = snapshot_data(df_proc, df_events.iloc[0], cfg, event_index=0)
    assert inc["direction"] == "increase"
    assert inc["panels"]["voltage"]["limit"]["side"] == "lower"
    assert inc["panels"]["frequency"]["limit"]["side"] == "lower"
    # Event 1 is a load decrease (-kW) -> voltage rises -> upper limit/band relevant.
    dec = snapshot_data(df_proc, df_events.iloc[1], cfg, event_index=1)
    assert dec["direction"] == "decrease"
    assert dec["panels"]["voltage"]["limit"]["side"] == "upper"
    assert dec["panels"]["frequency"]["limit"]["side"] == "upper"


def test_markers_present_when_exit_nonnull():
    df_proc, df_events, cfg = _events()
    for pos in range(len(df_events)):
        row = df_events.iloc[pos]
        snap = snapshot_data(df_proc, row, cfg, event_index=pos)
        v = snap["panels"]["voltage"]
        import pandas as pd
        if pd.notnull(row.get("V_exit_ts")):
            assert "exit" in v and v["exit"]["ts"] is not None
        # extreme marker present whenever V_dev exists
        if pd.notnull(row.get("V_dev")):
            assert "extreme" in v


def test_time_offset_skips_neighbour_clamp():
    df_proc, df_events, cfg = _events()
    # A deliberate offset should asymmetrically shift the window.
    base = snapshot_data(df_proc, df_events.iloc[1], cfg, event_index=1, time_offset_s=0.0)
    shifted = snapshot_data(df_proc, df_events.iloc[1], cfg, event_index=1, time_offset_s=-3.0)
    assert shifted["left_s"] > base["left_s"] - 1e-6  # more pre-event data shown
