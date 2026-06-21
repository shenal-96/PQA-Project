"""Tests for the local persistent usage log (desktop/usage_log.py).

Uses ``PQA_DATA_DIR`` to redirect the log into a tmp dir so the real per-user
app-data file is never touched. Covers the counters, atomic persistence across
"restarts" (re-import not needed — the module reads the file each call), the
session timer, corrupt-file resilience, and the HostBridge wiring.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from desktop import usage_log  # noqa: E402


@pytest.fixture
def tmp_log(tmp_path, monkeypatch):
    """Point the usage log at an isolated tmp dir and pin the username."""
    monkeypatch.setenv("PQA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(usage_log, "_current_user", lambda: "tester")
    return tmp_path


def test_data_dir_honours_override(tmp_log):
    assert usage_log.data_dir() == str(tmp_log)
    assert usage_log.log_path() == os.path.join(str(tmp_log), "usage_log.json")


def test_counters_accumulate_and_persist(tmp_log):
    usage_log.record_analysis_run()
    usage_log.record_analysis_run()
    usage_log.record_report_generated()
    usage_log.record_active_seconds(120)

    # Written to disk as JSON keyed by user.
    with open(usage_log.log_path(), encoding="utf-8") as f:
        raw = json.load(f)
    rec = raw["users"]["tester"]
    assert rec["analyses_run"] == 2
    assert rec["reports_generated"] == 1
    assert rec["active_seconds"] == 120
    assert rec["first_seen"] and rec["last_seen"]

    # read_usage derives active_hours.
    summary = usage_log.read_usage()["users"]["tester"]
    assert summary["active_hours"] == round(120 / 3600.0, 3)


def test_per_user_separation(tmp_log, monkeypatch):
    usage_log.record_analysis_run(user="alice")
    usage_log.record_analysis_run(user="bob")
    usage_log.record_report_generated(user="bob")
    users = usage_log.read_usage()["users"]
    assert users["alice"]["analyses_run"] == 1
    assert users["bob"]["analyses_run"] == 1
    assert users["bob"]["reports_generated"] == 1


def test_negative_and_bad_seconds_ignored(tmp_log):
    usage_log.record_active_seconds(-5)
    usage_log.record_active_seconds("nope")  # type: ignore[arg-type]
    usage_log.record_active_seconds(0)
    assert usage_log.read_usage()["users"] == {}


def test_corrupt_file_is_recovered(tmp_log):
    with open(usage_log.log_path(), "w", encoding="utf-8") as f:
        f.write("{ this is not json")
    # Does not raise; treats the file as empty and overwrites cleanly.
    usage_log.record_analysis_run()
    assert usage_log.read_usage()["users"]["tester"]["analyses_run"] == 1


def test_session_timer_records_session_and_time(tmp_log, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(usage_log.time, "monotonic", lambda: clock["t"])

    timer = usage_log.SessionTimer(flush_interval_s=60)
    timer.start()  # session start recorded; _last = 1000
    clock["t"] = 1030.0  # 30 s elapse
    timer.stop()  # final flush adds 30 s

    rec = usage_log.read_usage()["users"]["tester"]
    assert rec["sessions"] == 1
    assert rec["active_seconds"] == pytest.approx(30.0)


def test_bridge_increments_on_analysis_and_report(tmp_log):
    import base64

    from desktop.shell import HostBridge

    fixture = os.path.join(_HERE, "fixtures", "hioki_sample.csv")
    with open(fixture, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    bridge = HostBridge()
    bridge.load_csv({"csv_b64": b64})
    bridge.run_analysis({})

    summary = bridge.usage_summary()["users"]["tester"]
    assert summary["analyses_run"] == 1
    assert summary["reports_generated"] == 0
