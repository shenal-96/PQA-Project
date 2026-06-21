"""Pytest bootstrap: put the repo root on sys.path so ``import core.analysis`` works
regardless of the directory pytest is invoked from.
"""
import os
import sys
import tempfile

import pytest

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture(autouse=True)
def _isolate_usage_log(tmp_path_factory, monkeypatch):
    """Redirect the desktop usage log into a tmp dir for every test.

    The HostBridge increments usage counters on run_analysis/generate_report, so
    without this any bridge test would write to the developer's real
    ``%APPDATA%/PQA`` (or ``~/.local/share/PQA``) file. Tests that need to assert
    on the log set ``PQA_DATA_DIR`` themselves; this just keeps the default off
    real user data.
    """
    if "PQA_DATA_DIR" not in os.environ:
        monkeypatch.setenv("PQA_DATA_DIR",
                           str(tmp_path_factory.mktemp("pqa_usage")))
