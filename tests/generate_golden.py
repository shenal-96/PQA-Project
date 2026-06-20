"""Regenerate the golden parity files from the current engine.

Run this **only** when you have deliberately changed the engine and confirmed
the new numbers are correct:

    python tests/generate_golden.py

It overwrites ``tests/golden/*.json``. The committed golden files are the
contract the parity test enforces.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)                       # tests/  -> _scenarios, _parity_utils
sys.path.insert(0, os.path.dirname(_HERE))      # repo root -> core

from _parity_utils import canonical_events, proc_signature  # noqa: E402
from _scenarios import SCENARIOS, run_scenario              # noqa: E402

GOLDEN_DIR = os.path.join(_HERE, "golden")


def main() -> None:
    os.makedirs(GOLDEN_DIR, exist_ok=True)
    for scenario in SCENARIOS:
        df_proc, df_events = run_scenario(scenario)
        events = canonical_events(df_events)
        sig = proc_signature(df_proc)
        with open(os.path.join(GOLDEN_DIR, f"{scenario['name']}_events.json"), "w") as f:
            json.dump(events, f, indent=2)
        with open(os.path.join(GOLDEN_DIR, f"{scenario['name']}_proc_signature.json"), "w") as f:
            json.dump(sig, f, indent=2)
        print(f"[golden] {scenario['name']}: {len(events)} events, {sig['n_rows']} proc rows")


if __name__ == "__main__":
    main()
