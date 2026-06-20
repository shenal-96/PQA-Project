"""Parity scenarios: fixed (input CSV + config) pairs run through the engine.

Add a scenario here (e.g. a Miro fixture) and both the golden generator and the
parity test pick it up automatically.
"""
from __future__ import annotations

import os

_FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

SCENARIOS = [
    {
        "name": "hioki_iso",
        "csv": os.path.join(_FIX, "hioki_sample.csv"),
        "config": lambda ca: ca.AnalysisConfig.iso_8528_defaults(),
    },
]


def run_scenario(scenario: dict):
    """Load the scenario CSV and run ``perform_analysis``; return (df_proc, df_events)."""
    import core.analysis as ca

    df = ca.load_and_prepare_csv(scenario["csv"])
    cfg = scenario["config"](ca)
    return ca.perform_analysis(df, cfg)
