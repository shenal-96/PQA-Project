"""Tests for core.recalc (per-event overrides + recalculate compliance)."""
from __future__ import annotations

import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import core.analysis as ca                                       # noqa: E402
from core.recalc import apply_overrides, recompute_df_interp     # noqa: E402
from core.serialize import events_to_records                     # noqa: E402

FIXTURE = os.path.join(_HERE, "fixtures", "hioki_sample.csv")


def _setup():
    df = ca.load_and_prepare_csv(FIXTURE)
    cfg = ca.AnalysisConfig()
    df_proc, df_events = ca.perform_analysis(df, cfg)
    df_events = df_events.reset_index(drop=True)
    df_interp = recompute_df_interp(df_proc, cfg.skip_interpolation)
    return df_proc, df_events, df_interp, cfg


def test_empty_overrides_are_noop():
    _, df_events, df_interp, cfg = _setup()
    out = apply_overrides(df_events, df_interp, cfg, {})
    # Field-by-field equality via the same serializer used by the contract.
    assert events_to_records(out) == events_to_records(df_events)


def test_recompute_df_interp_grid():
    df_proc, _, df_interp, _ = _setup()
    # 100 ms interpolation produces more rows than the 1 Hz source.
    assert len(df_interp) > len(df_proc)
    assert "Timestamp" in df_interp.columns


def test_v_rec_override_changes_status():
    _, df_events, df_interp, cfg = _setup()
    # Force a voltage recovery time well over the ISO limit on event 0; if that
    # event had a voltage excursion, it must now Fail (and flag a potential fault).
    pos = 0
    has_v_exit = pd.notnull(df_events.iloc[pos].get("V_exit_ts"))
    out = apply_overrides(df_events, df_interp, cfg,
                          {"0": {"v_rec_override": 999.0}})
    assert out.iloc[pos]["V_rec_s"] == 999.0
    if has_v_exit:
        assert out.iloc[pos]["Compliance_Status"] == "Fail"
        assert bool(out.iloc[pos]["Potential_Fault"]) is True
    # Other events untouched.
    assert events_to_records(out.iloc[pos + 1:]) == events_to_records(df_events.iloc[pos + 1:])
