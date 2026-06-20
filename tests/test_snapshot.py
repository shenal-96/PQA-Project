"""Tests for core.viz_dataprep.snapshot_data (4-panel event snapshots)."""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import pandas as pd                                 # noqa: E402
import core.analysis as ca                          # noqa: E402
from core.viz_dataprep import snapshot_data, itic_curve  # noqa: E402

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


def test_snapshot_resampled_to_5hz():
    df_proc, df_events, cfg = _events()
    snap = snapshot_data(df_proc, df_events.iloc[0], cfg, event_index=0)
    ts = pd.to_datetime(snap["panels"]["voltage"]["timestamps"], format="ISO8601")
    diffs = ts.to_series().diff().dropna().dt.total_seconds().round(3)
    assert set(diffs.unique()) == {0.2}  # exactly 5 data points per second


def test_itic_curve_shape_and_classification():
    df_proc, df_events, cfg = _events()
    itic = itic_curve(df_events, cfg.nominal_voltage)
    assert itic["upper"] and itic["lower"]          # envelope polylines present
    assert all(len(pt) == 2 for pt in itic["upper"])
    assert len(itic["events"]) == 2                 # both hioki events are plottable
    for e in itic["events"]:
        assert set(e) == {"dur", "pct", "inside"}
        assert isinstance(e["inside"], bool)


def test_itic_curve_empty_events_still_has_envelope():
    itic = itic_curve(pd.DataFrame(), 415.0)
    assert itic["events"] == []
    assert itic["upper"] and itic["lower"]          # the curve is always drawable


def test_iso_8528_5_two_band_mode():
    df = ca.load_and_prepare_csv(FIXTURE)
    cfg = ca.AnalysisConfig(
        iso_8528_5_mode=True,
        freq_start_upper_increase=50.2, freq_start_lower_increase=49.85,
        freq_start_upper_decrease=50.15, freq_start_lower_decrease=49.8,
    )
    df_proc, df_events = ca.perform_analysis(df, cfg)
    df_events = df_events.reset_index(drop=True)
    # Engine exposes the β_f start band + §7 steady-state columns in ISO mode.
    for col in ("F_start_upper", "F_start_lower", "F_presstep_ok", "V_presstep_ok",
                "F_poststep_ok", "V_poststep_ok"):
        assert col in df_events.columns, col
    # Snapshot frequency panel carries the start band and the exit marker sits on it.
    snap = snapshot_data(df_proc, df_events.iloc[0], cfg, event_index=0)
    fp = snap["panels"]["frequency"]
    assert fp["start_band"] == {"upper": 50.2, "lower": 49.85}
    if "exit" in fp:
        assert fp["exit"]["value"] in (50.2, 49.85)     # on the β_f band, not α_f


def test_iso_mode_off_has_no_start_band():
    df_proc, df_events, cfg = _events()  # default cfg → ISO mode off
    snap = snapshot_data(df_proc, df_events.iloc[0], cfg, event_index=0)
    assert "start_band" not in snap["panels"]["frequency"]
    assert "F_start_upper" not in df_events.columns
