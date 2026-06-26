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


def test_report_steady_table_html():
    from desktop.report_host import build_steady_table_html

    assert build_steady_table_html(None) == ""
    assert build_steady_table_html(pd.DataFrame()) == ""

    v = np.full(60, 415.0)
    v[30] = 440.0
    df = _frame(60, v=v)
    steady = ca.analyze_steady_state(df, pd.DataFrame(), _cfg(rated_load_kw=500))
    html = build_steady_table_html(steady)
    assert "Steady-State Compliance" in html
    assert "<table" in html and "</table>" in html
    assert "Fail" in html                      # the out-of-band window
    assert "50%" in html                       # rated-load label
    assert "β_f" in html                       # new peak-to-peak frequency column


def test_report_steady_summary_html():
    from desktop.report_host import build_steady_summary_html

    assert build_steady_summary_html(None) == ""
    assert build_steady_summary_html({"n_windows": 0}) == ""

    df = _two_load_frame()
    cfg = _cfg(steady_performance_class="G2")
    steady = ca.analyze_steady_state(df, pd.DataFrame(), cfg, windows=_two_windows(df))
    html = build_steady_summary_html(ca.summarize_steady_state(df, steady, cfg))
    assert "Steady-State Summary" in html
    assert "ΔU_st" in html
    assert "Performance class G2" in html
    assert "no per-phase voltage" in html      # unbalance status (fixture has none)
    assert "insufficient sample rate" in html  # modulation sample-rate gate


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


# ── ISO 8528-5 performance class + Table 4 limits ────────────────────────────

def test_steady_limits_none_without_class():
    assert ca.steady_limits(_cfg()) is None


def test_steady_limits_resolves_class():
    lim = ca.steady_limits(_cfg(steady_performance_class="G3"))
    assert lim["freq_band_pct"] == 0.5       # β_f
    assert lim["volt_dev_pct"] == 1.0        # ΔU_st
    assert lim["freq_tol_band_pct"] == 2.0   # α_f
    assert lim["volt_modulation_pct"] == 0.3
    assert lim["freq_droop_pct"] == 0.0      # isochronous default → 0


def test_steady_limits_footnotes():
    # footnote a: single/two-cylinder raises β_f to 2.5 for any class
    lim = ca.steady_limits(_cfg(steady_performance_class="G3",
                                steady_single_two_cylinder=True))
    assert lim["freq_band_pct"] == 2.5
    # footnotes f/g: low-power relaxes ΔU_st to ±10
    lim = ca.steady_limits(_cfg(steady_performance_class="G3", steady_low_power=True))
    assert lim["volt_dev_pct"] == 10.0
    # footnote h: parallel operation tightens unbalance to 0.5
    lim = ca.steady_limits(_cfg(steady_performance_class="G2",
                                steady_parallel_operation=True))
    assert lim["volt_unbalance_pct"] == 0.5
    # footnote q: non-isochronous keeps the Table 4 droop figure
    lim = ca.steady_limits(_cfg(steady_performance_class="G2", steady_isochronous=False))
    assert lim["freq_droop_pct"] == 5.0


# ── β_f (steady-state frequency band, spec §2.1) ─────────────────────────────

def test_beta_f_value_informational_in_legacy_mode():
    f = np.full(60, 50.0); f[10] = 50.1; f[20] = 49.9   # p-p 0.2 Hz → β_f 0.4%
    df = _frame(60, f=f)
    row = ca.analyze_steady_state(df, pd.DataFrame(), _cfg()).iloc[0]
    assert row["Beta_f_pct"] == 0.4
    assert row["Beta_f_pass"] is None        # no class → informational only
    assert row["Status"] == "Pass"


def test_beta_f_graded_pass_fail_by_class():
    f = np.full(60, 50.0); f[10] = 50.2; f[20] = 49.8   # p-p 0.4 Hz → β_f 0.8%
    df = _frame(60, f=f)
    g3 = ca.analyze_steady_state(df, pd.DataFrame(), _cfg(steady_performance_class="G3")).iloc[0]
    assert g3["Beta_f_limit_pct"] == 0.5
    assert bool(g3["Beta_f_pass"]) is False  # 0.8 > 0.5
    assert g3["Status"] == "Fail"
    assert "β_f" in g3["Failure_Reasons"]
    g2 = ca.analyze_steady_state(df, pd.DataFrame(), _cfg(steady_performance_class="G2")).iloc[0]
    assert bool(g2["Beta_f_pass"]) is True   # 0.8 <= 1.5
    assert g2["Status"] == "Pass"


def test_class_mode_voltage_not_failed_per_window():
    # A per-sample voltage excursion fails legacy δU, but in class mode the
    # window verdict is β_f only (ΔU_st is cross-window) — so the window passes.
    v = np.full(60, 415.0); v[30] = 440.0
    df = _frame(60, v=v)
    assert ca.analyze_steady_state(df, pd.DataFrame(), _cfg()).iloc[0]["Status"] == "Fail"
    g2 = ca.analyze_steady_state(df, pd.DataFrame(), _cfg(steady_performance_class="G2")).iloc[0]
    assert g2["V_n_out"] == 1                 # still counted (informational)
    assert g2["Status"] == "Pass"             # β_f drives the class-mode verdict


# ── cross-window summary (ΔU_st, droop, gate, placeholders) ──────────────────

def _two_load_frame(n=121):
    """0..59 s at 415 V / 250 kW, 60.. s at 417 V / 500 kW (a step at 60 s)."""
    v = np.where(np.arange(n) < 60, 415.0, 417.0)
    df = _frame(n, v=v)
    df["Avg_kW"] = np.where(np.arange(n) < 60, 250.0, 500.0)
    return df


def _two_windows(df):
    ts = df["Timestamp"]
    return [{"start": ts.iloc[2], "end": ts.iloc[55]},
            {"start": ts.iloc[62], "end": ts.iloc[118]}]


def test_summary_delta_u_st():
    df = _two_load_frame()
    cfg = _cfg(steady_performance_class="G2")
    steady = ca.analyze_steady_state(df, pd.DataFrame(), cfg, windows=_two_windows(df))
    summ = ca.summarize_steady_state(df, steady, cfg)
    assert summ["delta_u_st_pct"] == round((417 - 415) / (2 * 415) * 100, 3)
    assert summ["delta_u_st_limit_pct"] == 2.5    # G2
    assert summ["delta_u_st_pass"] is True
    assert summ["n_windows"] == 2


def test_summary_droop_isochronous():
    df = _two_load_frame()                    # frequency flat at 50 across both loads
    cfg = _cfg(steady_performance_class="G3")
    steady = ca.analyze_steady_state(df, pd.DataFrame(), cfg, windows=_two_windows(df))
    summ = ca.summarize_steady_state(df, steady, cfg)
    assert summ["freq_droop_pct"] == 0.0
    assert summ["freq_droop_pass"] is True     # 0 within the isochronous tolerance


def test_summary_keys_and_sample_rate_gate():
    df = _frame(60)
    cfg = _cfg(steady_performance_class="G2")
    steady = ca.analyze_steady_state(df, pd.DataFrame(), cfg)
    summ = ca.summarize_steady_state(df, steady, cfg)
    for k in ("delta_u_st_pct", "freq_droop_pct", "volt_unbalance_status",
              "modulation_status", "sample_rate_hz", "performance_class", "limits"):
        assert k in summ
    assert summ["performance_class"] == "G2"
    assert summ["sample_rate_hz"] == 1.0       # _frame is 1 s spacing
    assert summ["volt_unbalance_status"] == "no per-phase voltage in data"  # _frame has none
    assert "insufficient sample rate" in summ["modulation_status"]          # 1 Hz < 50 Hz gate


def test_summary_empty_when_no_windows():
    summ = ca.summarize_steady_state(_frame(60), pd.DataFrame(),
                                     _cfg(steady_performance_class="G2"))
    assert summ["n_windows"] == 0
    assert summ["delta_u_st_pct"] is None


def test_bridge_includes_steady_summary_when_enabled():
    res = _bridge_with_csv().run_analysis(
        {"steady_state_enabled": True, "steady_dwell_min_s": 5, "steady_exclusion_s": 1,
         "steady_performance_class": "G2"})
    assert "steady_summary" in res
    s = res["steady_summary"]
    assert s["performance_class"] == "G2"
    assert "delta_u_st_pct" in s and "sample_rate_hz" in s


def test_bridge_omits_steady_summary_by_default():
    assert "steady_summary" not in _bridge_with_csv().run_analysis({})


# ── sample-rate gate (§4) + voltage unbalance (§2.4) ─────────────────────────

def test_voltage_unbalance_helper():
    assert ca._voltage_unbalance_pct(415, 415, 415) == 0.0      # balanced → 0
    assert 0.5 < ca._voltage_unbalance_pct(415, 415, 410) < 1.5
    assert ca._voltage_unbalance_pct(0, 0, 0) is None           # degenerate guard


def _frame_pp(n=60, vph=(415.0, 415.0, 410.0), kind="LN", start="2026-01-01 00:00:00"):
    """A flat in-band frame carrying the per-phase voltage frame on df.attrs
    (the same channel perform_analysis populates), kind = "LL" or "LN"."""
    ts = pd.date_range(start, periods=n, freq="1s")
    df = pd.DataFrame({
        "Timestamp": ts,
        "Avg_Voltage_LL": np.full(n, float(np.mean(vph))),
        "Avg_Frequency": np.full(n, 50.0),
        "Avg_kW": np.full(n, 250.0),
    })
    vp = pd.DataFrame({"Timestamp": ts})
    for i, val in enumerate(vph, 1):
        vp[f"V_ph{i}"] = float(val)
    df.attrs["v_phase"] = vp
    df.attrs["v_phase_kind"] = "L-L" if kind.upper().replace("-", "") == "LL" else "L-N"
    return df


def test_perform_analysis_retains_per_phase_on_attrs():
    ts = pd.date_range("2026-01-01", periods=30, freq="1s")
    raw = pd.DataFrame({"Timestamp": ts, "Freq_AVG": 50.0, "P_sum_AVG": 250000.0,
                        "U12_rms_AVG": 415.0, "U23_rms_AVG": 414.0, "U31_rms_AVG": 416.0})
    df_proc, _ = ca.perform_analysis(raw, ca.AnalysisConfig())
    # Per-phase rides on attrs, NOT as columns (which would leak into df_events).
    assert not any(c.startswith("V_ph") or c.startswith("V_LL") for c in df_proc.columns)
    assert df_proc.attrs.get("v_phase_kind") == "L-L"
    assert all(c in df_proc.attrs["v_phase"].columns for c in ("V_ph1", "V_ph2", "V_ph3"))
    raw_ln = raw.rename(columns={"U12_rms_AVG": "U1_rms_AVG", "U23_rms_AVG": "U2_rms_AVG",
                                 "U31_rms_AVG": "U3_rms_AVG"})
    df_ln, _ = ca.perform_analysis(raw_ln, ca.AnalysisConfig())
    assert df_ln.attrs.get("v_phase_kind") == "L-N"


def test_summary_unbalance_from_per_phase():
    df = _frame_pp(vph=(415.0, 415.0, 410.0), kind="LN")
    cfg = _cfg(steady_performance_class="G2")
    summ = ca.summarize_steady_state(df, ca.analyze_steady_state(df, pd.DataFrame(), cfg), cfg)
    assert summ["volt_unbalance_pct"] == round(ca._voltage_unbalance_pct(415, 415, 410), 3)
    assert "L-N" in summ["volt_unbalance_status"] and "approx" in summ["volt_unbalance_status"]
    assert summ["volt_unbalance_limit_pct"] == 1.0             # G2
    assert isinstance(summ["volt_unbalance_pass"], bool)


def test_summary_unbalance_ll_is_exact_label():
    df = _frame_pp(vph=(414.0, 415.0, 416.0), kind="LL")
    cfg = _cfg(steady_performance_class="G3")
    summ = ca.summarize_steady_state(df, ca.analyze_steady_state(df, pd.DataFrame(), cfg), cfg)
    assert "L-L magnitudes" in summ["volt_unbalance_status"]
    assert "approx" not in summ["volt_unbalance_status"]


def test_summary_unbalance_absent_when_no_per_phase():
    df = _frame(60)                                            # no V_LL/V_LN columns
    summ = ca.summarize_steady_state(df, ca.analyze_steady_state(df, pd.DataFrame(), _cfg()), _cfg())
    assert summ["volt_unbalance_pct"] is None
    assert summ["volt_unbalance_status"] == "no per-phase voltage in data"


def test_modulation_gate_insufficient_rate():
    df = _frame_pp(kind="LN")                                  # 1 s spacing → 1 Hz
    cfg = _cfg(steady_performance_class="G3")
    summ = ca.summarize_steady_state(df, ca.analyze_steady_state(df, pd.DataFrame(), cfg), cfg)
    assert "insufficient sample rate" in summ["modulation_status"]
    assert summ["modulation_pct"] is None


def test_modulation_gate_g1_is_amc():
    df = _frame_pp(kind="LN")
    cfg = _cfg(steady_performance_class="G1")
    summ = ca.summarize_steady_state(df, ca.analyze_steady_state(df, pd.DataFrame(), cfg), cfg)
    assert "AMC" in summ["modulation_status"]


def test_modulation_gate_adequate_rate_is_pending():
    ts = pd.date_range("2026-01-01 00:00:00", periods=600, freq=pd.Timedelta(milliseconds=10))
    df = pd.DataFrame({"Timestamp": ts, "Avg_Voltage_LL": 415.0, "Avg_Frequency": 50.0,
                       "Avg_kW": 250.0})
    cfg = _cfg(steady_performance_class="G3", steady_dwell_min_s=2.0, steady_exclusion_s=0.5)
    summ = ca.summarize_steady_state(df, ca.analyze_steady_state(df, pd.DataFrame(), cfg), cfg)
    assert summ["sample_rate_hz"] == 100.0
    assert "pending" in summ["modulation_status"]


def test_bridge_steady_summary_unbalance_and_gate():
    res = _bridge_with_csv().run_analysis(
        {"steady_state_enabled": True, "steady_dwell_min_s": 5, "steady_exclusion_s": 1,
         "steady_performance_class": "G2"})
    s = res["steady_summary"]
    assert isinstance(s["volt_unbalance_status"], str)
    assert "insufficient sample rate" in s["modulation_status"]   # fixture is ~1 s
