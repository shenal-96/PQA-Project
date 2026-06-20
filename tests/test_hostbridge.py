"""HostBridge backbone test: base64 CSV -> bridge -> JSON contract.

Verifies the local in-process path the Windows app uses, and that the bridge's
serialized events match a direct engine run through the same serializer (so the
contract introduces no drift).
"""
from __future__ import annotations

import base64
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

import core.analysis as ca                       # noqa: E402
from core.serialize import events_to_records     # noqa: E402
from desktop.shell import HostBridge             # noqa: E402

FIXTURE = os.path.join(_HERE, "fixtures", "hioki_sample.csv")


def _b64_fixture() -> str:
    with open(FIXTURE, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def test_caps():
    assert HostBridge().caps() == {"platform": "desktop", "canReport": True, "canXls": True}


def test_load_csv_metadata():
    meta = HostBridge().load_csv({"csv_b64": _b64_fixture(), "filename": "hioki_sample.csv"})
    assert meta["logger_format"] == "hioki"
    assert meta["valid"] is True
    assert meta["n_rows"] == 150
    assert "Freq_AVG" in meta["columns"]


def test_run_analysis_contract():
    bridge = HostBridge()
    bridge.load_csv({"csv_b64": _b64_fixture()})
    res = bridge.run_analysis({})

    # shape
    assert set(res) >= {"logger_format", "n_rows", "events", "metrics"}
    assert res["n_rows"] == 150
    assert len(res["events"]) == 2
    assert all("Compliance_Status" in e for e in res["events"])

    # metric series are JSON-safe and aligned to the processed frame
    v = res["metrics"]["Avg_Voltage_LL"]
    assert len(v["timestamps"]) == res["n_rows"] == len(v["values"])
    assert isinstance(v["timestamps"][0], str)  # ISO string

    # bridge events == direct engine run via the same serializer (no drift)
    df = ca.load_and_prepare_csv(FIXTURE)
    _, df_events = ca.perform_analysis(df, ca.AnalysisConfig())
    assert res["events"] == events_to_records(df_events)


def test_metric_series_requires_analysis():
    bridge = HostBridge()
    bridge.load_csv({"csv_b64": _b64_fixture()})
    try:
        bridge.metric_series("Avg_kW")
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError before run_analysis")
