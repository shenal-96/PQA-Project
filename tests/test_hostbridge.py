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


def test_load_csv_reports_time_range():
    meta = HostBridge().load_csv({"csv_b64": _b64_fixture()})
    assert meta["time_min"] and meta["time_max"]
    assert meta["time_min"] < meta["time_max"]


def test_run_analysis_includes_events_overlay():
    bridge = HostBridge()
    bridge.load_csv({"csv_b64": _b64_fixture()})
    res = bridge.run_analysis({})
    overlay = res["events_overlay"]
    assert len(overlay) == len(res["events"])
    assert all({"timestamp", "dKw", "label"} <= set(m) for m in overlay)
    # labels carry the signed kW step (e.g. "+220 kW" / "-160 kW")
    assert all("kW" in m["label"] for m in overlay)


def test_time_window_filters_events():
    bridge = HostBridge()
    meta = bridge.load_csv({"csv_b64": _b64_fixture()})
    full = bridge.run_analysis({})
    assert len(full["events"]) == 2

    # Restrict to the first half of the file → drops the later event(s).
    overlay_ts = [m["timestamp"] for m in full["events_overlay"]]
    cutoff = overlay_ts[0]  # window ending at the first event's timestamp
    windowed = bridge.run_analysis({"time_start": meta["time_min"], "time_end": cutoff})
    assert len(windowed["events"]) < len(full["events"])
    assert windowed["n_rows"] < full["n_rows"]

    # Re-running with no window restores the full result (raw frame is retained).
    restored = bridge.run_analysis({})
    assert len(restored["events"]) == 2


def test_time_window_empty_raises():
    bridge = HostBridge()
    bridge.load_csv({"csv_b64": _b64_fixture()})
    try:
        bridge.run_analysis({"time_start": "1999-01-01T00:00:00",
                             "time_end": "1999-01-01T01:00:00"})
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError for an empty time window")


def test_metric_series_requires_analysis():
    bridge = HostBridge()
    bridge.load_csv({"csv_b64": _b64_fixture()})
    try:
        bridge.metric_series("Avg_kW")
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError before run_analysis")


def test_derive_report_targets_multi_keeps_one_dir_and_stem():
    """One chosen Save path -> all artifacts in that folder, same stem, own ext."""
    import os
    from desktop.shell import _derive_report_targets

    files = [{"filename": "PQA_Report.pdf"}, {"filename": "PQA_Report.docx"}]
    targets = _derive_report_targets(os.path.join("/Users/me/Reports", "SiteX.pdf"), files)
    assert targets == [
        os.path.join("/Users/me/Reports", "SiteX.pdf"),
        os.path.join("/Users/me/Reports", "SiteX.docx"),
    ]


def test_derive_report_targets_single_preserves_path():
    import os
    from desktop.shell import _derive_report_targets

    targets = _derive_report_targets(os.path.join("/tmp", "My Report.html"),
                                     [{"filename": "x.html"}])
    assert targets == [os.path.join("/tmp", "My Report.html")]
