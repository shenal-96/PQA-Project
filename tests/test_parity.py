"""Parity tests — the central correctness proof for the migration.

Assert that ``core.analysis.perform_analysis`` reproduces the committed golden
results (event-by-event, field-by-field, floats within 1e-6) on fixed inputs.
The same harness will later assert the Pyodide/iPad path matches these numbers.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from _parity_utils import canonical_events, deep_diff, proc_signature  # noqa: E402
from _scenarios import SCENARIOS, run_scenario                         # noqa: E402

GOLDEN_DIR = os.path.join(_HERE, "golden")
_IDS = [s["name"] for s in SCENARIOS]


def _load_golden(name: str) -> dict | list:
    with open(os.path.join(GOLDEN_DIR, name)) as f:
        return json.load(f)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_IDS)
def test_events_parity(scenario):
    _, df_events = run_scenario(scenario)
    golden = _load_golden(f"{scenario['name']}_events.json")
    diffs = deep_diff(golden, canonical_events(df_events))
    assert not diffs, "df_events drift vs golden:\n" + "\n".join(diffs[:40])


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_IDS)
def test_proc_signature_parity(scenario):
    df_proc, _ = run_scenario(scenario)
    golden = _load_golden(f"{scenario['name']}_proc_signature.json")
    diffs = deep_diff(golden, proc_signature(df_proc))
    assert not diffs, "df_proc signature drift vs golden:\n" + "\n".join(diffs[:40])


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_IDS)
def test_scenario_produces_events(scenario):
    """Guard: the fixtures must actually exercise event detection."""
    _, df_events = run_scenario(scenario)
    assert len(df_events) >= 1
