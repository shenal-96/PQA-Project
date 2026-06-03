"""
ecu_reference.py — MTU ECU 8 / ECU 9 SAE J1939 reference (UI-free).

Loads the structured data extracted from the MTU J1939 Functional Description
(E532424/06E) by scripts/extract_ecu_j1939.py, and overlays curated
control-philosophy / performance-effect notes for the genset-relevant
*controllable* parameters.

Data sections (see assets/ecu9_j1939.json):
  * config_params  — editable ECU config (Section 5, via DiaSys)
  * command_pgns   — PGNs the ECU RECEIVES (controllable)
  * telemetry_pgns — PGNs the ECU TRANSMITS (read-only monitoring)
  * fault_codes    — diagnostic trouble codes (DTC)

This module has no Streamlit imports — keep it that way (project convention).

NOTE: This document is the J1939 *interface* spec. The deep engine-tuning
values (governor PID, fuel limits, the actual droop-curve percentages) are
NOT here — they live in a separate MTU parameter-list / Application &
Installation manual. OHECS lets you *select* among pre-programmed droop
curves; it does not define them.
"""

from __future__ import annotations

import json
import os

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_JSON_PATH = os.path.join(_APP_DIR, "assets", "ecu9_j1939.json")

# Key genset-relevant command PGNs to surface first (in this order).
PRIORITY_COMMAND_PGNS = [0, 52992, 65366, 64915, 65281, 65365, 64971, 65441]

# Transport/protocol-plumbing PGNs — captured but not operationally useful
# as "settings". Hidden from the headline command view by default.
_TRANSPORT_PGNS = {59904, 59302, 60416, 60160, 60928}

# Curated control-philosophy / performance-effect notes, keyed by SPN string.
# Focused on the parameters a genset/external controller actually drives.
EFFECTS = {
    # --- TSC1 (PGN 0) — the primary engine command ---
    "695": ("Selects what TSC1 controls: speed, torque, or speed/torque "
            "limit. 'Speed control' is normal genset governing.",
            "Wrong mode = the ECU ignores your speed request or runs torque-"
            "limited; must be 'Speed control' for isochronous genset running."),
    "897": ("Priority of this override request vs other controllers on the "
            "bus (highest→low).",
            "If too low, another device's request wins; the genset controller "
            "normally uses high/highest so its speed demand is authoritative."),
    "898": ("The requested engine speed (or speed limit) in rpm — this is the "
            "governor setpoint the genset controller sends.",
            "Directly sets running speed → output frequency (e.g. 1500 rpm = "
            "50 Hz, 1800 rpm = 60 Hz). Ramp/step here drives the frequency "
            "transient the PQA tool measures."),
    "518": ("Requested engine torque or torque limit, as % of reference "
            "torque (−125…125%).",
            "Caps or commands load torque; used for load ramping / limiting. "
            "Lower limit = engine sheds load, protecting against overload."),
    "3349": ("How often TSC1 is transmitted (transmission rate).",
             "Too slow = sluggish/steppy speed control and poor transient "
             "recovery; matches setpoint 2.0502.007 (TSC1 Cycle Time)."),
    "3350": ("Declares the purpose of the TSC1 command (e.g. governing, "
             "limiting).",
             "Lets the ECU arbitrate competing requests correctly."),
    # --- CTL (PGN 52992) — continuous limits ---
    "1785": ("Maximum continuous engine speed limit (0–8000 rpm).",
             "Hard ceiling on governed speed → caps maximum frequency; "
             "protects against overspeed from a runaway speed request."),
    "1787": ("Maximum continuous engine torque limit (0–125%).",
             "Caps sustained load the engine will accept → de-rating / "
             "overload protection. Lower = earlier load limiting under heavy "
             "block loads."),
    # --- GC1 (PGN 64915) — generator control ---
    "3542": ("Requested engine control mode: Normal / Rapid / Emergency "
             "shutdown, Normal / Rapid start.",
             "Selects start/stop behaviour. Rapid/Emergency skip cool-down — "
             "use only for protection events (cuts turbo/engine life)."),
    "4079": ("Generator governing speed command: Rated speed vs Low Idle.",
             "Switches between full-speed (on-load) and idle (warm-up/cool-"
             "down). Running at rated under no load wastes fuel; idle on load "
             "starves the set."),
    # --- OHECS (PGN 64971) — droop / rating selection ---
    "2881": ("Selects the active droop curve for Accelerator 1: Normal, or "
             "one of 13 pre-programmed alternate droop settings.",
             "Droop sets how much speed sags with load — critical for "
             "load-sharing between paralleled sets and for frequency "
             "stability. Higher droop = more frequency sag but stabler "
             "sharing; isochronous (0 droop) = flat frequency, needs active "
             "load sharing. The curve *values* live in the separate parameter "
             "manual; here you only pick which curve is active."),
    "2882": ("Selects engine power rating: default (max power) or a lower "
             "alternate rating.",
             "Lower rating = reduced fuelling/power across the range "
             "(de-rate for altitude, fuel quality, or longevity). Affects "
             "maximum block-load the set can take."),
    "2883": ("Selects default vs alternate low-idle speed point.",
             "Higher idle warms faster / supports hotel loads; lower idle "
             "saves fuel but cools slower."),
    "2884": ("Enables/disables the auxiliary governor.",
             "Auxiliary governor provides an alternate speed-control path; "
             "misconfiguration can fight the primary governor."),
    "1377": ("Engine synchronization switch (enable engine-side sync logic).",
             "Engages synchronising behaviour ahead of breaker close; only "
             "relevant when paralleling."),
    # --- ESS (PGN 65281) — start/stop over CAN ---
    "520568": ("CAN-commanded engine stop request.",
               "Remote stop path; asserting it shuts the engine down."),
    "520569": ("CAN-commanded engine start (MCS).",
               "Remote start path; the genset controller cranks the engine "
               "via this."),
    "520570": ("CAN start-lock — inhibits starting.",
               "Safety interlock; when active the engine cannot be started "
               "(maintenance lockout)."),
    # --- MSOSC1 (PGN 65365) — operating-station commands ---
    "520192": ("Engine start command from the operating station.",
               "Primary start trigger; edge/level starts the crank sequence."),
    "520193": ("Engine stop command from the operating station.",
               "Primary stop trigger; initiates the normal stop sequence."),
    "520194": ("Engine safety & protection override command.",
               "DANGER: when acknowledged, disables safety/protection "
               "shutdowns. Emergency-run only — engine damage / hazard risk. "
               "Never leave asserted."),
    "520197": ("Engine overspeed-test command.",
               "Commissioning test of the overspeed trip; only for "
               "controlled testing."),
    # --- MSCCES (PGN 65366) — speed adjust ---
    "521090": ("Requested operating speed (0–8031 rpm) from the operating "
               "station.",
               "Alternative speed setpoint path → sets frequency. Same "
               "performance role as TSC1 SPN 898."),
    "520207": ("Operating speed-up switch (increment speed).",
               "Trims speed/frequency up; used for manual frequency matching "
               "before synchronising."),
    "520208": ("Operating speed-down switch (decrement speed).",
               "Trims speed/frequency down for matching."),
    "520842": ("Requested speed-limit switch — limits requested speed to an "
               "internal parametrised value via ramp.",
               "Soft speed ceiling applied on a ramp; smooths speed "
               "limiting."),
    # --- MPL (PGN 65441) — power limitation ---
    "520745": ("Engine power limit request — maximum continuous (0–10000 kW).",
               "Hard cap on continuous output power → de-rate / overload "
               "protection at the power (kW) level rather than torque %."),
}


_DATA = None


def load():
    """Load and cache the ECU JSON. Returns the full dict."""
    global _DATA
    if _DATA is None:
        with open(_JSON_PATH, "r", encoding="utf-8") as f:
            _DATA = json.load(f)
    return _DATA


def meta():
    return load().get("meta", {})


def config_params():
    return load().get("config_params", [])


def command_pgns(include_transport=False):
    """Controllable PGNs (received), priority-ordered. Transport PGNs hidden
    unless include_transport=True."""
    pgns = load().get("command_pgns", [])
    if not include_transport:
        pgns = [p for p in pgns if p["pgn"] not in _TRANSPORT_PGNS]
    order = {p: i for i, p in enumerate(PRIORITY_COMMAND_PGNS)}
    return sorted(pgns, key=lambda p: (order.get(p["pgn"], 999), p["pgn"]))


def telemetry_pgns():
    return load().get("telemetry_pgns", [])


def fault_codes():
    return load().get("fault_codes", [])


def effect_for(spn):
    """Return (philosophy, performance) tuple for an SPN, or None."""
    return EFFECTS.get(str(spn))


def search_spns(query, sections=("command", "telemetry"), ecu9_only=False):
    """
    Search PGN parameters (SPNs) across the chosen sections.
    Returns list of dicts: {section, pgn, pgn_name, spn(dict)}.
    """
    query = (query or "").strip().lower()
    terms = [t for t in query.split() if t]
    results = []
    buckets = []
    if "command" in sections:
        buckets.append(("command", command_pgns()))
    if "telemetry" in sections:
        buckets.append(("telemetry", telemetry_pgns()))
    for section, pgns in buckets:
        for pgn in pgns:
            for spn in pgn["spns"]:
                if ecu9_only and not spn.get("ecu9"):
                    continue
                hay = f"{pgn['name']} {spn['name']} {spn['spn']} " \
                      f"{spn.get('unit','')}".lower()
                if all(t in hay for t in terms):
                    results.append({
                        "section": section,
                        "pgn": pgn["pgn"],
                        "pgn_name": pgn["name"],
                        "spn": spn,
                    })
    return results


def search_faults(query):
    """Search fault codes by SPN, FMI, alarm no., or designation text."""
    query = (query or "").strip().lower()
    terms = [t for t in query.split() if t]
    out = []
    for f in fault_codes():
        hay = f"{f['spn']} {f['fmi']} {f.get('alarm_no','')} " \
              f"{f['name']}".lower()
        if all(t in hay for t in terms):
            out.append(f)
    return out


def counts():
    d = load()
    return {
        "config": len(d.get("config_params", [])),
        "command_pgns": len(command_pgns()),
        "command_spns": sum(len(p["spns"]) for p in command_pgns()),
        "telemetry_pgns": len(d.get("telemetry_pgns", [])),
        "telemetry_spns": sum(len(p["spns"])
                              for p in d.get("telemetry_pgns", [])),
        "faults": len(d.get("fault_codes", [])),
    }
