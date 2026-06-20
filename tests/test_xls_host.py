"""Tests for the M4 XLS tabs: desktop.xls_host + HostBridge XLS methods.

Tiers, like test_report.py:
  * Set Point **CSV** comparison needs only pandas → runs in the lean CI job.
  * WinScope / ECU-recording / Set Point **XLS** need python_calamine (and
    openpyxl to author the fixtures); they ``importorskip`` so they run locally
    and skip in CI.
"""
from __future__ import annotations

import base64
import datetime
import io
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from desktop import xls_host                          # noqa: E402
from desktop.shell import HostBridge                  # noqa: E402

ECU_FIXTURE = os.path.join(_ROOT, "testShenal.xls")


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _comap_csv(rows) -> bytes:
    """ComAp CSV: 4 skipped lines, a header, then ``Group;Sub-group;Name;Value;Dimension``."""
    lines = ["m1", "m2", "m3", "m4", "Group;Sub-group;Name;Value;Dimension"]
    lines += [";".join(str(c) for c in r) for r in rows]
    return "\n".join(lines).encode("utf-8")


def _param_xlsx(overspeed) -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Parameter"
    ws.append([1, "Nominal RPM", 1500, "rpm"])
    ws.append([2, "Overspeed", overspeed, "rpm"])
    ws.append([3, "Nominal Voltage", 415, "V"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _winscope_xlsx() -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append(["PC Time", "Generator Voltage L1-L2 (Q)", "Generator Voltage L2-L3 (Q)",
               "Generator Voltage L3-L1 (Q)", "Generator Current L1", "Generator Current L2",
               "Generator Current L3", "Generator Frequency", "Generator Power Factor",
               "Generator P"])
    t0 = datetime.datetime(2026, 1, 1, 9, 0, 0)
    for i in range(60):
        kw = 100 if i < 20 else (350 if i < 40 else 180)
        freq = 49.6 if i == 20 else 50.0
        ws.append([t0 + datetime.timedelta(seconds=i), 415, 415, 415,
                   kw / 0.7, kw / 0.7, kw / 0.7, freq, 0.9, kw])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Set Point comparison — CSV (CI-safe) ────────────────────────────────────────

def test_compare_setpoint_csv_finds_differences():
    f1 = _comap_csv([("Engine", "Speed", "Nominal RPM", 1500, "rpm"),
                     ("Engine", "Speed", "Overspeed", 1650, "rpm"),
                     ("Gen", "Volt", "Nominal", 415, "V")])
    f2 = _comap_csv([("Engine", "Speed", "Nominal RPM", 1500, "rpm"),
                     ("Engine", "Speed", "Overspeed", 1800, "rpm"),
                     ("Gen", "Volt", "Nominal", 400, "V")])
    res = xls_host.compare_setpoint({"kind": "csv", "files": [
        {"filename": "UnitA.csv", "b64": _b64(f1)},
        {"filename": "UnitB.csv", "b64": _b64(f2)},
    ]})
    assert res["kind"] == "csv"
    assert res["labels"] == ["UnitA", "UnitB"]
    assert res["columns"] == ["Group", "Sub-group", "Name", "Dimension", "UnitA", "UnitB"]
    assert res["n_diffs"] == 2
    names = {r["Name"] for r in res["rows"]}
    assert names == {"Overspeed", "Nominal"}
    # JSON-safe rows carry per-file values.
    overspeed = next(r for r in res["rows"] if r["Name"] == "Overspeed")
    assert str(overspeed["UnitA"]) == "1650" and str(overspeed["UnitB"]) == "1800"


def test_compare_setpoint_requires_two_files():
    with pytest.raises(ValueError):
        xls_host.compare_setpoint({"kind": "csv", "files": [{"filename": "a.csv", "b64": _b64(b"x")}]})


def test_compare_setpoint_uniquifies_labels():
    f = _comap_csv([("G", "S", "P", 1, "u")])
    f2 = _comap_csv([("G", "S", "P", 2, "u")])
    res = xls_host.compare_setpoint({"kind": "csv", "files": [
        {"filename": "dup.csv", "b64": _b64(f)},
        {"filename": "dup.csv", "b64": _b64(f2)},
    ]})
    assert res["labels"][0] == "dup" and res["labels"][1] != "dup"


# ── Set Point comparison — XLS (needs calamine + openpyxl) ───────────────────────

def test_compare_setpoint_xls():
    pytest.importorskip("python_calamine")
    res = xls_host.compare_setpoint({"kind": "xls", "files": [
        {"filename": "UnitA.xlsx", "b64": _b64(_param_xlsx(1650))},
        {"filename": "UnitB.xlsx", "b64": _b64(_param_xlsx(1800))},
    ]})
    assert res["columns"][:4] == ["Sheet", "Nr", "Name", "Location"]
    assert res["n_diffs"] == 1
    row = res["rows"][0]
    assert row["Sheet"] == "Parameter" and row["Name"] == "Overspeed"
    assert float(row["UnitA"]) == 1650.0 and float(row["UnitB"]) == 1800.0


# ── WinScope (needs calamine + openpyxl) ────────────────────────────────────────

def test_load_winscope_via_bridge_and_analyze():
    pytest.importorskip("python_calamine")
    bridge = HostBridge()
    meta = bridge.load_winscope({"filename": "site.xlsx", "b64": _b64(_winscope_xlsx())})
    assert meta["valid"] is True
    assert meta["logger_format"] == "winscope"
    assert meta["n_rows"] == 60
    res = bridge.run_analysis({"load_threshold_kw": 50})
    assert bridge._config.skip_interpolation is True       # winscope skips interpolation
    assert len(res["events"]) >= 1
    assert all("Compliance_Status" in e for e in res["events"])


# ── ECU recording (needs calamine; uses the committed fixture) ──────────────────

@pytest.mark.skipif(not os.path.exists(ECU_FIXTURE), reason="ECU fixture missing")
def test_ecu_recording_via_bridge():
    pytest.importorskip("python_calamine")
    with open(ECU_FIXTURE, "rb") as f:
        res = HostBridge().ecu_recording({"filename": "testShenal.xls", "b64": _b64(f.read())})
    assert res["n_rows"] > 0
    assert len(res["channels"]) >= 1
    # every channel series is aligned to the timestamp axis
    n = len(res["timestamps"])
    assert all(len(v) == n for v in res["channels"].values())
    # grouping + humanised labels are present
    assert sum(len(v) for v in res["groups"].values()) == len(res["channels"])
    assert all(name in res["labels"] for name in res["channels"])
    assert isinstance(res["timestamps"][0], str)            # ISO string


def test_ecu_recording_requires_b64():
    with pytest.raises(Exception):
        HostBridge().ecu_recording({"filename": "x.xls"})
