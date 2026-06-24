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
ECU_FIXTURE = os.path.join(ROOT, "testShenal.xls")
OUT_DIR = os.path.join(ROOT, "web", "src", "dev")


def _comap_csv(rows) -> bytes:
    """A tiny ComAp config CSV (4 skipped lines + header + data)."""
    lines = ["meta", "meta", "meta", "meta", "Group;Sub-group;Name;Value;Dimension"]
    lines += [";".join(str(c) for c in r) for r in rows]
    return "\n".join(lines).encode("utf-8")


def _gen_setpoint(bridge) -> dict:
    """Synthetic Set Point CSV diff so the browser preview shows a populated table."""
    a = _comap_csv([("Engine", "Speed", "Nominal RPM", 1500, "rpm"),
                    ("Engine", "Speed", "Overspeed", 1650, "rpm"),
                    ("Gen", "Voltage", "Nominal", 415, "V"),
                    ("Gen", "Voltage", "Over-voltage", 460, "V")])
    b = _comap_csv([("Engine", "Speed", "Nominal RPM", 1500, "rpm"),
                    ("Engine", "Speed", "Overspeed", 1800, "rpm"),
                    ("Gen", "Voltage", "Nominal", 400, "V"),
                    ("Gen", "Voltage", "Over-voltage", 460, "V")])
    return bridge.compare_setpoint({"kind": "csv", "files": [
        {"filename": "UnitA.csv", "b64": base64.b64encode(a).decode("ascii")},
        {"filename": "UnitB.csv", "b64": base64.b64encode(b).decode("ascii")},
    ]})


def main() -> None:
    bridge = HostBridge()
    with open(FIXTURE, "rb") as f:
        meta = bridge.load_csv({"csv_b64": base64.b64encode(f.read()).decode("ascii"),
                                "filename": "hioki_sample.csv"})
    # Enable steady-state (ISO 8528-5 δ bands) with relaxed dwell thresholds so
    # the short demo fixture yields a couple of dwell windows for the browser
    # preview of the SteadyStatePanel.
    result = bridge.run_analysis({
        "steady_state_enabled": True,
        "steady_dwell_min_s": 10,
        "steady_exclusion_s": 3,
        "rated_load_kw": 500,
    })
    snapshots = [bridge.snapshot({"index": i}) for i in range(len(result["events"]))]

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "sample_result.json"), "w") as f:
        json.dump(result, f, indent=2)
    with open(os.path.join(OUT_DIR, "sample_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    with open(os.path.join(OUT_DIR, "sample_snapshots.json"), "w") as f:
        json.dump(snapshots, f, indent=2)
    print(f"wrote sample_result.json: {len(result['events'])} events, {result['n_rows']} rows; "
          f"{len(snapshots)} snapshots")

    # --- M4 XLS-tab samples (so the MockBackend can demo WinScope/SetPoint/ECU) ---
    setpoint = _gen_setpoint(bridge)
    with open(os.path.join(OUT_DIR, "sample_setpoint.json"), "w") as f:
        json.dump(setpoint, f, indent=2)
    print(f"wrote sample_setpoint.json: {setpoint['n_diffs']} diffs, {setpoint['n_files']} files")

    if os.path.exists(ECU_FIXTURE):
        with open(ECU_FIXTURE, "rb") as f:
            ecu = bridge.ecu_recording({"filename": "testShenal.xls",
                                        "b64": base64.b64encode(f.read()).decode("ascii")})
        with open(os.path.join(OUT_DIR, "sample_ecu.json"), "w") as f:
            json.dump(ecu, f)
        print(f"wrote sample_ecu.json: {ecu['n_rows']} rows, {len(ecu['channels'])} channels")
    else:
        print("skip sample_ecu.json (testShenal.xls missing)")


if __name__ == "__main__":
    main()
