"""
extract_ecu_j1939.py — Parse the MTU ECU 8/ECU 9 SAE J1939 Functional
Description PDF (E532424/06E) into structured JSON for the Settings
Reference / ECU Reference UI.

Produces assets/ecu9_j1939.json with four sections:
  * config_params  — Section 5 editable ECU config parameters (ZKP)
  * command_pgns   — PGNs the ECU RECEIVES (controllable: TSC1, OHECS, ...)
  * telemetry_pgns — PGNs the ECU TRANSMITS (read-only monitoring data)
  * fault_codes    — Section 6 diagnostic trouble codes (DTC)

The command vs telemetry split is derived from the per-SPN T (transmit) /
R (receive) columns in the source tables.

Usage:
    python scripts/extract_ecu_j1939.py "manuals_inbox/E532424_06E - Functional Description SAE J1939.pdf"

This is a build-time tool — not imported by the app. The app reads the JSON.
"""

import json
import re
import sys
from pathlib import Path

import fitz  # pymupdf


PDF_DEFAULT = ("manuals_inbox/E532424_06E - Functional Description "
               "SAE J1939.pdf")
OUT_PATH = "assets/ecu9_j1939.json"


def clean_name(s):
    """Join hyphenated line breaks, collapse whitespace."""
    if not s:
        return ""
    s = s.replace("-\n", "").replace("\n", " ")
    return re.sub(r"\s+", " ", s).strip()


def clean_val(s):
    """Strip line breaks inside a value cell (e.g. 'd\\ne\\ng' -> 'deg')."""
    if not s:
        return ""
    return s.replace("\n", "").strip()


def find_header_row(rows):
    """Return index of the SPN table header row (contains 'SPN' and 'Byte')."""
    for i, row in enumerate(rows):
        cells = [clean_val(c or "") for c in row]
        if "SPN" in cells and "Byte" in cells:
            return i
    return None


def col_map(header):
    """Map logical column name -> index from a header row."""
    m = {}
    for i, c in enumerate(header):
        c = clean_val(c or "").lower()
        if c == "t":
            m["T"] = i
        elif c == "r":
            m["R"] = i
        elif "zkp" in c:
            m["zkp"] = i
        elif "subgroup" in c or "name" in c:
            m.setdefault("name", i)
        elif c == "spn":
            m["spn"] = i
        elif c == "byte":
            m["byte"] = i
        elif c == "length":
            m["length"] = i
        elif "resolut" in c:
            m["res"] = i
        elif c == "min":
            m["min"] = i
        elif c == "max":
            m["max"] = i
        elif c == "unit":
            m["unit"] = i
        elif c == "8":
            m["ecu8"] = i
        elif c == "9":
            m["ecu9"] = i
    return m


def parse_pgn_page_range(doc, start_idx, end_idx):
    """
    Parse one PGN section spanning PDF page indices [start_idx, end_idx).
    Returns (general_dict, spn_list, has_receive).
    """
    general = {}
    spns = []
    has_receive = False

    for p in range(start_idx, end_idx):
        page = doc[p]
        tabs = page.find_tables()
        for t in tabs.tables:
            rows = t.extract()
            if not rows:
                continue
            head = [clean_val(c or "") for c in rows[0]]

            # General header table
            if "Identifier" in head and "PGN (hex)" in head:
                if len(rows) > 1:
                    vals = rows[1]
                    for hname, v in zip(head, vals):
                        general[clean_val(hname)] = clean_val(v or "")
                continue

            # SPN table
            hidx = find_header_row(rows)
            if hidx is None:
                continue
            cm = col_map(rows[hidx])
            if "spn" not in cm or "name" not in cm:
                continue
            for row in rows[hidx + 1:]:
                def get(key):
                    i = cm.get(key)
                    if i is None or i >= len(row):
                        return ""
                    return clean_val(row[i] or "")

                spn = get("spn")
                name = clean_name(row[cm["name"]] if cm["name"] < len(row)
                                  else "")
                # skip pure state-enumeration / continuation rows
                if not spn or not name:
                    continue
                t_flag = get("T")
                r_flag = get("R")
                if r_flag:
                    has_receive = True
                rng = ""
                lo, hi = get("min"), get("max")
                if lo or hi:
                    rng = f"{lo} … {hi}".strip(" …")
                spns.append({
                    "name": name,
                    "spn": spn,
                    "zkp": get("zkp"),
                    "byte": get("byte"),
                    "length": get("length"),
                    "resolution": get("res"),
                    "range": rng,
                    "unit": clean_val(row[cm["unit"]] if "unit" in cm
                                      and cm["unit"] < len(row) else ""),
                    "ecu9": bool(get("ecu9")),
                    "transmit": bool(t_flag),
                    "receive": bool(r_flag),
                })
    return general, spns, has_receive


def parse_pgns(doc, toc):
    """Walk all PGN TOC entries and parse each section."""
    entries = []
    for lvl, title, page in toc:
        m = re.search(r"PGN\s+(\d+)", title)
        if m:
            entries.append((int(m.group(1)), title.strip(), page))

    command, telemetry = [], []
    for i, (pgn_num, title, page) in enumerate(entries):
        start_idx = page - 1  # TOC pages are 1-based
        # end = next PGN entry's page, or fault list start
        end_idx = entries[i + 1][2] - 1 if i + 1 < len(entries) else page
        end_idx = max(end_idx, start_idx + 1)

        general, spns, has_recv = parse_pgn_page_range(doc, start_idx, end_idx)
        if not spns:
            continue
        # Clean PGN display name: drop the "3.2.x PGN NNN - " prefix
        disp = re.sub(r"^\d+(\.\d+)*\s+PGN\s+\d+\s*[-–]\s*", "", title).strip()
        rec = {
            "pgn": pgn_num,
            "pgn_hex": general.get("PGN (hex)", ""),
            "name": disp,
            "cycle": general.get("Cycle time", ""),
            "priority": general.get("Default Pri- ority")
            or general.get("Default Priority", ""),
            "page": page,
            "spns": spns,
        }
        # Classify: any received SPN -> command; else telemetry
        if has_recv:
            command.append(rec)
        else:
            telemetry.append(rec)
    return command, telemetry


def parse_fault_codes(doc, start_page=240, end_page=290):
    """Parse the DTC tables in Section 6 (pages are 1-based here)."""
    faults = []
    seen = set()
    for p in range(start_page - 1, min(end_page, doc.page_count)):
        tabs = doc[p].find_tables()
        for t in tabs.tables:
            rows = t.extract()
            if not rows:
                continue
            # locate header with SPN / FMI / Designation
            hidx = None
            for i, row in enumerate(rows):
                cells = [clean_val(c or "") for c in row]
                if "SPN" in cells and "FMI" in cells:
                    hidx = i
                    break
            if hidx is None:
                continue
            head = [clean_val(c or "") for c in rows[hidx]]
            ci = {}
            for i, c in enumerate(head):
                cl = c.lower()
                if c == "SPN":
                    ci["spn"] = i
                elif c == "FMI":
                    ci["fmi"] = i
                elif "designation" in cl:
                    ci["name"] = i
                elif "no." in cl or "alarm" in cl:
                    ci.setdefault("alarm", i)
            if "spn" not in ci or "name" not in ci:
                continue
            for row in rows[hidx + 1:]:
                def g(k):
                    i = ci.get(k)
                    return clean_val(row[i] or "") if i is not None \
                        and i < len(row) else ""
                spn, fmi, name = g("spn"), g("fmi"), clean_name(
                    row[ci["name"]] if ci["name"] < len(row) else "")
                if not name or not spn:
                    continue
                key = (spn, fmi, name)
                if key in seen:
                    continue
                seen.add(key)
                faults.append({
                    "spn": spn, "fmi": fmi,
                    "alarm_no": g("alarm"), "name": name,
                })
    return faults


def parse_config_params(doc):
    """Section 5 editable config params — small, parsed from text reliably."""
    # These are stable; transcribe from the parsed Section 5 text (p237-238).
    return [
        {"zkp": "2.0502.002", "name": "J1939 Node Number (ECU)",
         "range": "00h – 253", "default": "00h",
         "description": "CAN source address the ECU communicates under on the "
         "J1939 bus. Set via DiaSys; takes effect after restart.",
         "ecu9_only": False},
        {"zkp": "2.0502.006", "name": "J1939 External Controller Node Number",
         "range": "00h – 253", "default": "EAh (234)",
         "description": "Node number the ECU uses to receive messages from the "
         "external/generator controller (third-party controller).",
         "ecu9_only": True},
        {"zkp": "2.0500.001", "name": "CAN Interface Configuration",
         "range": "0 – 65535", "default": "—",
         "description": "When J1939 is active, the PCS-5 protocol must be set "
         "Inactive (0) or Automatic Transmission (66).",
         "ecu9_only": False},
        {"zkp": "2.0502.001", "name": "J1939 Status",
         "range": "0 – 1", "default": "0 (Off)",
         "description": "Master enable for the J1939 protocol. 0 = Off, 1 = On.",
         "ecu9_only": False},
        {"zkp": "2.0502.003", "name": "Speed Dependent Transmission Time",
         "range": "5 – 100 ms", "default": "20 ms",
         "description": "Time difference applied when transmitting a J1939 "
         "message depending on engine speed.",
         "ecu9_only": False},
        {"zkp": "2.0502.004", "name": "J1939 Generator Controller Node Number",
         "range": "00 – 253", "default": "EAh (234)",
         "description": "Node number the ECU receives generator-controller "
         "messages from. (ECU 8 only.)",
         "ecu9_only": False},
        {"zkp": "2.0502.005", "name": "DM1 Delete",
         "range": "0 – 1", "default": "0",
         "description": "Allows active faults (DM1) to be deleted with DM3 (0) "
         "or DM11 (1) for downward compatibility. (ECU 8 only.)",
         "ecu9_only": False},
        {"zkp": "2.0502.007", "name": "TSC 1 Cycle Time",
         "range": "0 – 1000 s", "default": "0.01 s",
         "description": "Transmission cycle time for the TSC1 torque/speed "
         "control message. (ECU 9 only.)",
         "ecu9_only": True},
    ]


def main():
    pdf = sys.argv[1] if len(sys.argv) > 1 else PDF_DEFAULT
    doc = fitz.open(pdf)
    toc = doc.get_toc()

    command, telemetry = parse_pgns(doc, toc)
    faults = parse_fault_codes(doc)
    config = parse_config_params(doc)

    data = {
        "meta": {
            "source": "MTU ECU 8 / ECU 9 SAE J1939 Functional Description",
            "doc_ref": "E532424/06E (2019-07)",
            "note": "J1939 communication interface spec. Editable config is "
                    "limited to Section 5; command PGNs are controllable; "
                    "telemetry PGNs are read-only. Deep engine-tuning values "
                    "(governor/fuel/droop curves) live in a separate MTU "
                    "parameter-list manual.",
        },
        "config_params": config,
        "command_pgns": command,
        "telemetry_pgns": telemetry,
        "fault_codes": faults,
    }

    Path("assets").mkdir(exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Wrote {OUT_PATH}")
    print(f"  config_params:  {len(config)}")
    print(f"  command_pgns:   {len(command)} "
          f"({sum(len(p['spns']) for p in command)} SPNs)")
    print(f"  telemetry_pgns: {len(telemetry)} "
          f"({sum(len(p['spns']) for p in telemetry)} SPNs)")
    print(f"  fault_codes:    {len(faults)}")
    print("\nCommand PGNs:")
    for p in command:
        print(f"  PGN {p['pgn']:>6} {p['name'][:50]:50} "
              f"{len(p['spns'])} SPNs")


if __name__ == "__main__":
    main()
