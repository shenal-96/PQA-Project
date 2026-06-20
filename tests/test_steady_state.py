"""Steady-state (ISO 8528-5 δ band) analysis: engine + bridge contract.

Covers dwell-window segmentation, per-window δ-band pass/fail, hunting
detection, and the HostBridge wiring (opt-in `steady` contract key +
recalc_steady for the hybrid confirm flow).
"""
from __future__ import annotations

import base64
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

import core.analysis as ca                       # noqa: E402
from desktop.shell import HostBridge             # noqa: E402

FIXTURE = os.path.join(_HERE, "fixtures", "hioki_sample.csv")


def _frame(n=121, v=415.0, f=50.0, start="2026-01-01 00:00:00"):
    """A flat in-band df_proc at 1 s spacing (v/f may be scalars or arrays)."""
    ts = pd.date_range(start, periods=n, freq="1s")
    return pd.DataFrame({
        "Timestamp": ts,
        "Avg_Voltage_LL": np.full(n, v) if np.isscalar(v) else v,
        "Avg_Frequency": np.full(n, f) if np.isscalar(f) else f,
        "Avg_kW": np.full(n, 250.0),
    })


def _events(ts_pairs, start="2026-01-01 00:00:00"):
    """df_events with Start/End timestamps at the given (start_s, end_s) offsets."""
    base = pd.Timestamp(start)
    rows = [{"Start_Timestamp": base + pd.Timedelta(seconds=a),
             "End_Timestamp": base + pd.Timedelta(seconds=b),
             "dKw": 100.0} for a, b in ts_pairs]
    return pd.DataFrame(rows)


def _cfg(**kw):
    c = ca.AnalysisConfig(steady_state_enabled=True, steady_exclusion_s=5.0,
                          steady_dwell_min_s=10.0)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


# ── window detection ─────────────────────────────────────────────────────────

def test_detect_windows_brackets_events():
    df = _frame(121)                       # 0..120 s
    ev = _events([(40, 42), (80, 82)])     # two load steps
    wins = ca.detect_steady_windows(df, ev, _cfg())
    # before first (5..35), between (47..75), after (87..115) — all >= 10 s.
    assert len(wins) == 3
    secs = [(w["end"] - w["start"]).total_seconds() for w in wins]
    assert all(s >= 10 for s in secs)
    assert wins[0]["start"] == df["Timestamp"].iloc[0] + pd.Timedelta(seconds=5)


def test_detect_windows_drops_short_gaps():
    df = _frame(121)
    ev = _events([(40, 42), (50, 52)])     # gap 42->50 = 8 s, minus 2x5 excl -> negative
    wins = ca.detect_steady_windows(df, ev, _cfg())
    # before (5..35) and after (57..115) survive; the tiny middle gap does not.
    assert len(wins) == 2


def test_detect_windows_no_events_is_whole_record():
    df = _frame(121)
    wins = ca.detect_steady_windows(df, pd.DataFrame(), _cfg())
    assert len(wins) == 1


# ── per-window evaluation ────────────────────────────────────────────────────

def test_window_in_band_passes():
    df = _frame(60)
    steady = ca.analyze_steady_state(df, pd.DataFrame(), _cfg(steady_dwell_min_s=10.0))
    assert len(steady) == 1
    row = steady.iloc[0]
    assert row["Status"] == "Pass"
    assert row["V_n_out"] == 0 and row["F_n_out"] == 0


def test_window_out_of_band_fails():
    v = np.full(60, 415.0)
    v[30] = 440.0                          # one voltage excursion above δU band
    df = _frame(60, v=v)
    steady = ca.analyze_steady_state(df, pd.DataFrame(), _cfg())
    row = steady.iloc[0]
    assert row["Status"] == "Fail"
    assert row["V_n_out"] == 1
    assert "Voltage out of" in row["Failure_Reasons"]
    assert row["V_worst_dev_pct"] > 2.5


def test_load_label_from_rated():
    df = _frame(60)                        # Avg_kW = 250
    steady = ca.analyze_steady_state(df, pd.DataFrame(), _cfg(rated_load_kw=500))
    assert steady.iloc[0]["Load_Label"] == "50%"
    assert steady.iloc[0]["Load_Pct"] == 50.0


def test_hunting_flagged_but_in_band_passes():
    # Sustained oscillation that stays inside the δf band (±1 Hz here).
    t = np.arange(60)
    f = 50.0 + 0.6 * np.sin(2 * np.pi * t / 6.0)   # ~10 cycles, p-p 1.2 Hz
    df = _frame(60, f=f)
    steady = ca.analyze_steady_state(df, pd.DataFrame(), _cfg())
    row = steady.iloc[0]
    assert row["Status"] == "Pass"         # never leaves the band
    assert bool(row["Hunting"]) is True
    assert "Frequency oscillation" in row["Hunting_Reasons"]


def test_flat_signal_not_flagged_as_hunting():
    df = _frame(60)
    row = ca.analyze_steady_state(df, pd.DataFrame(), _cfg()).iloc[0]
    assert bool(row["Hunting"]) is False


# ── bridge contract ──────────────────────────────────────────────────────────

def _bridge_with_csv():
    bridge = HostBridge()
    with open(FIXTURE, "rb") as fh:
        bridge.load_csv({"csv_b64": base64.b64encode(fh.read()).decode("ascii")})
    return bridge


def test_bridge_omits_steady_by_default():
    res = _bridge_with_csv().run_analysis({})
    assert "steady" not in res


def test_bridge_includes_steady_when_enabled():
    res = _bridge_with_csv().run_analysis(
        {"steady_state_enabled": True, "steady_dwell_min_s": 5, "steady_exclusion_s": 1})
    assert "steady" in res
    assert isinstance(res["steady"], list)
    if res["steady"]:
        w = res["steady"][0]
        assert {"Start_Timestamp", "End_Timestamp", "Status", "V_n_out"} <= set(w)
        assert isinstance(w["Start_Timestamp"], str)   # JSON-safe ISO string


def test_recalc_steady_uses_supplied_windows():
    bridge = _bridge_with_csv()
    bridge.run_analysis({"steady_state_enabled": True, "steady_dwell_min_s": 5,
                         "steady_exclusion_s": 1})
    proc = bridge._df_proc
    t0, t1 = proc["Timestamp"].iloc[5], proc["Timestamp"].iloc[40]
    out = bridge.recalc_steady({"windows": [
        {"start": t0.isoformat(), "end": t1.isoformat(), "label": "Custom 50%"},
    ]})
    assert len(out["steady"]) == 1
    assert out["steady"][0]["Load_Label"] == "Custom 50%"
