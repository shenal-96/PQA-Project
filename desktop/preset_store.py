"""Persistent custom-preset library (desktop only).

User-defined acceptance presets are stored in the durable per-user app-data dir
(``presets.json`` beside the usage log — see :func:`desktop.usage_log.data_dir`)
so they survive restarts/reinstalls and can be exported and shared, unlike the
browser-``localStorage`` store the in-browser fallback uses.

Each preset is ``{"name": str, "values": {field: number|bool|str}}``. Validation
is permissive on the value set but strict on shape: a malformed file degrades to
an empty list rather than raising, only well-formed entries are kept, and names
are de-duplicated (last one wins on write, first on read).
"""
from __future__ import annotations

import json
import os
import tempfile

from desktop import usage_log

_PRESETS_FILENAME = "presets.json"
_SCHEMA_VERSION = 1


def presets_path() -> str:
    """Absolute path to the custom-preset JSON file."""
    return os.path.join(usage_log.data_dir(), _PRESETS_FILENAME)


def _coerce_value(v):
    """Keep only JSON-scalar values a preset field may hold (num/bool/str)."""
    if isinstance(v, bool) or isinstance(v, (int, float)) or isinstance(v, str):
        return v
    return None


def _clean_preset(p) -> dict | None:
    """Return a well-formed ``{name, values}`` dict, or ``None`` if unusable."""
    if not isinstance(p, dict):
        return None
    name = p.get("name")
    values = p.get("values")
    if not isinstance(name, str) or not name.strip() or not isinstance(values, dict):
        return None
    clean: dict = {}
    for k, v in values.items():
        cv = _coerce_value(v)
        if isinstance(k, str) and cv is not None:
            clean[k] = cv
    return {"name": name.strip(), "values": clean}


def _clean_list(arr) -> list:
    """Validate + de-duplicate (by name) a list of presets, preserving order."""
    out: list = []
    seen: set = set()
    if isinstance(arr, list):
        for p in arr:
            cp = _clean_preset(p)
            if cp and cp["name"] not in seen:
                seen.add(cp["name"])
                out.append(cp)
    return out


def read_presets() -> list:
    """All stored custom presets (cleaned); ``[]`` on a missing/corrupt file."""
    try:
        with open(presets_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except Exception:  # noqa: BLE001 — corrupt/unreadable -> no presets
        return []
    if isinstance(data, dict):  # {"version": N, "presets": [...]}
        data = data.get("presets", [])
    return _clean_list(data)


def write_presets(presets) -> list:
    """Atomically persist the given preset list; returns the cleaned list."""
    cleaned = _clean_list(presets)
    payload = {"version": _SCHEMA_VERSION, "presets": cleaned}
    path = presets_path()
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".pqa_presets_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return cleaned
