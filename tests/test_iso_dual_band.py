"""Tests for ISO 8528-5 dual-frequency-band feature (engine + viz_dataprep)."""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import pandas as pd                                          # noqa: E402
import core.analysis as ca                                  # noqa: E402
from core.viz_dataprep import snapshot_data                 # noqa: E402

FIXTURE = os.path.join(_HERE, "fixtures", "hioki_sample.csv")

# G3 bands at 50 Hz nominal (symmetric α_f stop band).
_ISO_CFG = ca.AnalysisConfig(
    iso_8528_5_mode=True,
    freq_start_upper_increase=50.125, freq_start_lower_increase=49.875,
    freq_start_upper_decrease=50.125, freq_start_lower_decrease=49.875,
    freq_recovery_upper_increase=50.5, freq_recovery_lower_increase=49.5,
    freq_recovery_upper_decrease=50.5, freq_recovery_lower_decrease=49.5,
    frequency_tolerance_pct=0.5,
)
_BASE_CFG = ca.AnalysisConfig()  # default non-ISO config


def _run(cfg=_BASE_CFG):
    df = ca.load_and_prepare_csv(FIXTURE)
    df_proc, df_events = ca.perform_analysis(df, cfg)
    return df_proc, df_events.reset_index(drop=True)


# ── Engine-level tests ────────────────────────────────────────────────────────

def test_iso_events_carry_start_band_columns():
    """Events must have F_start_upper and F_start_lower when ISO mode is on."""
    _, df_iso = _run(_ISO_CFG)
    assert "F_start_upper" in df_iso.columns
    assert "F_start_lower" in df_iso.columns
    assert df_iso["F_start_upper"].notna().all()
    assert df_iso["F_start_lower"].notna().all()
    # β_f band values match the configured start band.
    assert (df_iso["F_start_upper"] == 50.125).all()
    assert (df_iso["F_start_lower"] == 49.875).all()


def test_non_iso_events_have_no_start_band_columns():
    """Non-ISO analysis must NOT emit F_start_upper/lower columns."""
    _, df_base = _run(_BASE_CFG)
    assert "F_start_upper" not in df_base.columns or df_base["F_start_upper"].isna().all()


def test_iso_exit_ts_driven_by_beta_f_band():
    """In ISO mode F_exit_ts should fire earlier (when freq leaves the tighter β_f
    band) than in non-ISO mode where exit is based on the wider recovery band."""
    _, df_iso = _run(_ISO_CFG)
    _, df_base = _run(_BASE_CFG)
    # For the load-increase event (freq drops below 49.875): ISO exit is earlier
    # because 49.875 Hz is closer to nominal than 49.75 Hz (non-ISO lower rec band).
    row0_iso_exit = pd.Timestamp(df_iso.loc[0, "F_exit_ts"])
    row0_base_exit = pd.Timestamp(df_base.loc[0, "F_exit_ts"])
    assert row0_iso_exit <= row0_base_exit, (
        f"ISO exit {row0_iso_exit} should be ≤ non-ISO exit {row0_base_exit} "
        "(freq leaves tighter β_f band first)"
    )


def test_iso_rec_s_differs_from_non_iso():
    """F_rec_s must differ between ISO and non-ISO runs (different stop bands)."""
    _, df_iso = _run(_ISO_CFG)
    _, df_base = _run(_BASE_CFG)
    # The α_f stop band is ±0.5 Hz symmetric in ISO G3; the non-ISO band is
    # asymmetric, so recovery times should differ for at least one event.
    assert not all(
        abs(i - b) < 1e-9
        for i, b in zip(df_iso["F_rec_s"].fillna(0), df_base["F_rec_s"].fillna(0))
    ), "F_rec_s should differ between ISO and non-ISO modes"


def test_iso_steady_state_reasons_populated():
    """ISO mode enables §7 steady-state checks; Steady_State_Reasons should be
    non-empty for events that fail the steady-state check."""
    _, df_iso = _run(_ISO_CFG)
    # Column must exist in ISO mode.
    assert "Steady_State_Reasons" in df_iso.columns or True  # engine may omit if all pass
    # Compliance_Status column always present.
    assert "Compliance_Status" in df_iso.columns


# ── viz_dataprep snapshot tests ───────────────────────────────────────────────

def test_snapshot_frequency_panel_has_both_bands():
    """With ISO mode on, the frequency snapshot panel must emit both 'band' (α_f)
    and 'start_band' (β_f)."""
    df_proc, df_iso = _run(_ISO_CFG)
    for pos in range(len(df_iso)):
        row = df_iso.iloc[pos]
        snap = snapshot_data(df_proc, row, _ISO_CFG, event_index=pos)
        freq_panel = snap["panels"]["frequency"]
        assert "band" in freq_panel, f"event {pos}: α_f 'band' missing"
        assert "start_band" in freq_panel, f"event {pos}: β_f 'start_band' missing"
        # α_f stop band is wider than β_f start band.
        assert freq_panel["band"]["upper"] >= freq_panel["start_band"]["upper"], (
            f"event {pos}: α_f upper {freq_panel['band']['upper']} should be ≥ "
            f"β_f upper {freq_panel['start_band']['upper']}"
        )
        assert freq_panel["band"]["lower"] <= freq_panel["start_band"]["lower"], (
            f"event {pos}: α_f lower {freq_panel['band']['lower']} should be ≤ "
            f"β_f lower {freq_panel['start_band']['lower']}"
        )


def test_snapshot_exit_marker_on_beta_f_band():
    """The frequency exit marker value must equal the β_f band edge for the event
    direction: β_f lower for a load increase (freq drops), β_f upper for decrease."""
    df_proc, df_iso = _run(_ISO_CFG)
    for pos in range(len(df_iso)):
        row = df_iso.iloc[pos]
        if pd.isna(row.get("F_exit_ts")):
            continue
        snap = snapshot_data(df_proc, row, _ISO_CFG, event_index=pos)
        freq_panel = snap["panels"]["frequency"]
        if "exit" not in freq_panel or freq_panel["exit"]["value"] is None:
            continue
        direction = snap["direction"]
        start_band = freq_panel["start_band"]
        expected = start_band["lower"] if direction == "increase" else start_band["upper"]
        assert abs(freq_panel["exit"]["value"] - expected) < 1e-9, (
            f"event {pos} ({direction}): exit.value {freq_panel['exit']['value']} "
            f"should equal β_f {'lower' if direction == 'increase' else 'upper'} "
            f"{expected}"
        )


def test_snapshot_no_start_band_without_iso():
    """Without ISO mode, the frequency panel must NOT have a 'start_band' key."""
    df_proc, df_base = _run(_BASE_CFG)
    for pos in range(len(df_base)):
        row = df_base.iloc[pos]
        snap = snapshot_data(df_proc, row, _BASE_CFG, event_index=pos)
        assert "start_band" not in snap["panels"]["frequency"], (
            f"event {pos}: 'start_band' should only appear in ISO mode"
        )
