"""Tests for the persistent custom-preset store + its bridge methods.

The store writes ``presets.json`` into ``usage_log.data_dir()``, which honours the
``PQA_DATA_DIR`` env override — so each test points it at a fresh tmp dir.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

import desktop.preset_store as ps          # noqa: E402
from desktop.shell import HostBridge        # noqa: E402


def test_write_then_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("PQA_DATA_DIR", str(tmp_path))
    presets = [
        {"name": "Site X", "values": {"voltage_tolerance_pct": 1.0, "apply_asymmetric_freq": True}},
        {"name": "Site Y", "values": {"frequency_tolerance_pct": 0.5}},
    ]
    written = ps.write_presets(presets)
    assert [p["name"] for p in written] == ["Site X", "Site Y"]
    assert ps.read_presets() == written
    # File really exists in the data dir, wrapped with a schema version.
    on_disk = json.loads((tmp_path / "presets.json").read_text())
    assert on_disk["version"] == ps._SCHEMA_VERSION
    assert len(on_disk["presets"]) == 2


def test_missing_file_reads_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("PQA_DATA_DIR", str(tmp_path))
    assert ps.read_presets() == []


def test_corrupt_file_reads_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("PQA_DATA_DIR", str(tmp_path))
    (tmp_path / "presets.json").write_text("{not valid json")
    assert ps.read_presets() == []


def test_malformed_entries_are_dropped(tmp_path, monkeypatch):
    monkeypatch.setenv("PQA_DATA_DIR", str(tmp_path))
    written = ps.write_presets([
        {"name": "Good", "values": {"voltage_tolerance_pct": 2.0}},
        {"name": "", "values": {}},                 # blank name -> dropped
        {"values": {"x": 1}},                        # no name -> dropped
        {"name": "BadValues", "values": "nope"},     # values not a dict -> dropped
        "garbage",                                    # not a dict -> dropped
    ])
    assert [p["name"] for p in written] == ["Good"]


def test_duplicate_names_deduped_keeping_first(tmp_path, monkeypatch):
    monkeypatch.setenv("PQA_DATA_DIR", str(tmp_path))
    written = ps.write_presets([
        {"name": "Dup", "values": {"a": 1}},
        {"name": "Dup", "values": {"a": 2}},
    ])
    assert len(written) == 1
    assert written[0]["values"] == {"a": 1}


def test_non_scalar_values_are_stripped(tmp_path, monkeypatch):
    monkeypatch.setenv("PQA_DATA_DIR", str(tmp_path))
    written = ps.write_presets([
        {"name": "P", "values": {"ok_num": 3, "ok_bool": False, "ok_str": "abs",
                                  "bad_list": [1, 2], "bad_obj": {"k": 1}}},
    ])
    assert written[0]["values"] == {"ok_num": 3, "ok_bool": False, "ok_str": "abs"}


def test_bridge_list_and_save_presets(tmp_path, monkeypatch):
    monkeypatch.setenv("PQA_DATA_DIR", str(tmp_path))
    bridge = HostBridge()
    assert bridge.list_presets() == {"presets": []}
    res = bridge.save_presets({"presets": [{"name": "Site Z", "values": {"frequency_recovery_time_s": 3.0}}]})
    assert res["presets"][0]["name"] == "Site Z"
    assert bridge.list_presets()["presets"] == res["presets"]
