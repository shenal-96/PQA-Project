"""Generate dev-mode sample data for the browser MockBackend.

Runs the real HostBridge on the committed Hioki fixture and dumps the exact JSON
contract to ``web/src/dev/``. This lets the frontend render real analysis output
in a plain browser (no PyWebview, no server) for UI development and CI build
checks. Re-run after changing the contract:

    python web/scripts/gen_sample.py
"""
from __future__ import annotations

import base64
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from desktop.shell import HostBridge  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "hioki_sample.csv")
OUT_DIR = os.path.join(ROOT, "web", "src", "dev")


def main() -> None:
    bridge = HostBridge()
    with open(FIXTURE, "rb") as f:
        meta = bridge.load_csv({"csv_b64": base64.b64encode(f.read()).decode("ascii"),
                                "filename": "hioki_sample.csv"})
    result = bridge.run_analysis({})

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "sample_result.json"), "w") as f:
        json.dump(result, f, indent=2)
    with open(os.path.join(OUT_DIR, "sample_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"wrote sample_result.json: {len(result['events'])} events, {result['n_rows']} rows")


if __name__ == "__main__":
    main()
