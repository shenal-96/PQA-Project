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
import urllib.parse

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


def test_log_error_writes_jsonl_and_counts(tmp_log):
    usage_log.log_error("csv_format_invalid", "missing Freq column", filename="x.csv")
    entries = usage_log.read_errors()
    assert len(entries) == 1
    e = entries[0]
    assert e["type"] == "error"
    assert e["category"] == "csv_format_invalid"
    assert e["message"] == "missing Freq column"
    assert e["details"]["filename"] == "x.csv"
    # rolling error count lands on the usage record too
    assert usage_log.read_usage()["users"]["tester"]["errors_logged"] == 1


def test_log_crash_captures_traceback(tmp_log):
    try:
        raise ValueError("boom")
    except ValueError as exc:
        usage_log.log_crash(exc, context="unit-test")
    entries = usage_log.read_errors()
    assert len(entries) == 1
    e = entries[0]
    assert e["type"] == "crash"
    assert e["error_type"] == "ValueError"
    assert e["message"] == "boom"
    assert e["context"] == "unit-test"
    assert "ValueError: boom" in e["traceback"]


def test_read_errors_respects_limit_and_order(tmp_log):
    for i in range(5):
        usage_log.log_error("cat", f"msg{i}")
    last2 = usage_log.read_errors(limit=2)
    assert [e["message"] for e in last2] == ["msg3", "msg4"]


def test_error_log_rotates_when_oversized(tmp_log, monkeypatch):
    monkeypatch.setattr(usage_log, "_ERROR_LOG_MAX_BYTES", 200)
    monkeypatch.setattr(usage_log, "_ERROR_LOG_KEEP_LINES", 3)
    for i in range(50):
        usage_log.log_error("cat", f"message-number-{i}")
    entries = usage_log.read_errors(limit=1000)
    # rotation kept only a small tail, and the newest entry survived
    assert len(entries) <= 4
    assert entries[-1]["message"] == "message-number-49"


def test_bridge_logs_crash_and_reraises(tmp_log):
    from desktop.shell import HostBridge

    bridge = HostBridge()
    with pytest.raises(RuntimeError):
        bridge.run_analysis({})  # no CSV loaded -> RuntimeError, logged then re-raised

    errors = bridge.recent_errors()["errors"]
    assert any(e["type"] == "crash" and e["context"] == "run_analysis" for e in errors)


def test_pending_crash_marker_lifecycle(tmp_log):
    assert usage_log.has_pending_crash() is None
    try:
        raise RuntimeError("hard crash")
    except RuntimeError as exc:
        usage_log.log_crash(exc, context="sys.excepthook", uncaught=True)
    pending = usage_log.has_pending_crash()
    assert pending is not None
    assert pending["error_type"] == "RuntimeError"
    assert pending["message"] == "hard crash"
    usage_log.clear_pending_crash()
    assert usage_log.has_pending_crash() is None


def test_caught_crash_does_not_mark_pending(tmp_log):
    try:
        raise ValueError("handled")
    except ValueError as exc:
        usage_log.log_crash(exc, context="bridge")  # uncaught defaults False
    assert usage_log.has_pending_crash() is None


def test_build_crash_report_contains_metadata_and_entries(tmp_log):
    usage_log.log_error("csv_format_invalid", "bad header", filename="x.csv")
    try:
        raise KeyError("missing")
    except KeyError as exc:
        usage_log.log_crash(exc, context="run_analysis", uncaught=True)
    report = usage_log.build_crash_report(app_version="1.2.3")
    assert "PQA Desktop — Crash / Error Report" in report
    assert "App version: 1.2.3" in report
    assert "csv_format_invalid" in report
    assert "KeyError" in report
    assert "Last unreported crash" in report


def test_send_crash_report_writes_file_and_clears_pending(tmp_log, monkeypatch):
    from desktop import crash_report

    # Stub the outward-facing actions so the test never opens a real mail client.
    opened = {}
    monkeypatch.setattr(crash_report.webbrowser, "open",
                        lambda url: opened.setdefault("url", url) or True)
    monkeypatch.setattr(crash_report, "reveal_in_file_manager", lambda path: True)

    try:
        raise RuntimeError("kaboom")
    except RuntimeError as exc:
        usage_log.log_crash(exc, context="sys.excepthook", uncaught=True)

    res = crash_report.send_crash_report(reveal=True)
    assert res["ok"] is True
    assert res["email"] == "sperera@penskeanz.com"
    assert res["mailto_opened"] is True
    assert opened["url"].startswith("mailto:sperera@penskeanz.com?")
    assert "kaboom" in urllib.parse.unquote(opened["url"])
    assert os.path.exists(res["report_path"])
    # pending marker cleared so the next launch won't re-prompt
    assert usage_log.has_pending_crash() is None


def test_bridge_crash_report_methods(tmp_log, monkeypatch):
    from desktop import crash_report
    from desktop.shell import HostBridge

    monkeypatch.setattr(crash_report.webbrowser, "open", lambda url: True)
    monkeypatch.setattr(crash_report, "reveal_in_file_manager", lambda path: True)

    bridge = HostBridge()
    assert bridge.pending_crash()["pending"] is None

    # A failed bridge call records a (caught) crash but not a pending marker.
    with pytest.raises(RuntimeError):
        bridge.run_analysis({})
    assert bridge.pending_crash()["pending"] is None

    # Simulate a hard crash, then verify the email + dismiss paths.
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        usage_log.log_crash(exc, context="sys.excepthook", uncaught=True)
    assert bridge.pending_crash()["pending"]["error_type"] == "RuntimeError"

    out = bridge.email_crash_report({})
    assert out["ok"] is True and out["email"] == "sperera@penskeanz.com"
    assert bridge.pending_crash()["pending"] is None


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
