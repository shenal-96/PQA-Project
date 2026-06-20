"""Tests for the JSON contract (core.serialize) and chart data-prep (core.viz_dataprep).

Guards that nothing pandas/numpy-typed leaks across the boundary — the contract
must be plain JSON so the same shapes work for the future Pyodide backend.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import core.analysis as ca                                            # noqa: E402
from core.serialize import analysis_result, events_to_records        # noqa: E402
from core.viz_dataprep import detected_events_overlay                # noqa: E402

FIXTURE = os.path.join(_HERE, "fixtures", "hioki_sample.csv")


def _run():
    df = ca.load_and_prepare_csv(FIXTURE)
    return ca.perform_analysis(df, ca.AnalysisConfig())


def test_contract_is_json_serialisable():
    df_proc, df_events = _run()
    payload = analysis_result(df_proc, df_events)
    # Round-trips through JSON without custom encoders -> proves no pandas types leak.
    again = json.loads(json.dumps(payload))
    assert again["n_rows"] == len(df_proc)
    assert len(again["events"]) == len(df_events)
    assert "Avg_kW" in again["metrics"]


def test_events_records_types():
    _, df_events = _run()
    recs = events_to_records(df_events)
    row = recs[0]
    assert isinstance(row["Compliance_Status"], str)
    assert isinstance(row["dKw"], float)
    assert isinstance(row["Start_Timestamp"], str)  # ISO timestamp


def test_detected_events_overlay():
    _, df_events = _run()
    overlay = detected_events_overlay(df_events)
    assert len(overlay) == len(df_events)
    assert overlay[0]["label"].endswith("kW")
    assert overlay[0]["timestamp"] is not None
    # increase then decrease in the fixture
    assert overlay[0]["dKw"] > 0 and overlay[1]["dKw"] < 0
