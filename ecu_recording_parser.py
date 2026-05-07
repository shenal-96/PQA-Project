"""
ECU Recording Parser

Reads time-series ECU recording files (XLS/XLSX) into a normalised DataFrame
and classifies channels into named groups (Temperatures, Pressures, etc.)
based on column-name keyword heuristics.

Pure data — no Streamlit / UI dependencies. Mirrors the conventions of
ecu_parser.py and ecu_csv_parser.py but for time-series logger data rather
than parameter snapshots.
"""

from __future__ import annotations

import os
import re
import pandas as pd


# Hints for picking the timestamp column. STRONG hints uniquely identify the
# datetime column; WEAK hints catch generic "time" columns and require the
# values to actually parse as datetimes (otherwise we'd grab elapsed-seconds
# columns like "TIME_§s").
_STRONG_TS_HINTS = ("datetime", "date_time", "date-time", "timestamp", "pc time", "logtime", "log time")
_WEAK_TS_HINTS = ("date", "time")


# Order matters — first match wins. Each entry: (group_name, (keyword, ...)).
# Keywords are matched against the lowercased column name with substring search.
_GROUP_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("Temperatures", ("temp", "°c", "coolant", "exhaust", "egt", "intake t", "ambient t", "oil t")),
    ("Pressures",    ("press", "_bar", "kpa", "psi", "mbar", "boost", "manifold p", "oil p")),
    ("Speeds",       ("rpm", "speed", "freq")),
    ("Power",        ("power", "kw", "kva", "kvar", "load")),
    ("Electrical",   ("volt", "current", "amp", "power factor", "_pf_", " pf ")),
    ("Fuel/Flow",    ("fuel", "flow", "consumption", "lph", "g/h")),
    ("Levels",       ("level", "%")),
]


def _values_parse_as_datetime(values, threshold: float = 0.7) -> bool:
    """Return True if ≥threshold fraction of non-null values parse as datetimes."""
    s = pd.Series(values).dropna()
    if len(s) == 0:
        return False
    cleaned = s.astype(str).map(_clean_timestamp_string)
    parsed = pd.to_datetime(cleaned, errors="coerce")
    return parsed.notna().mean() >= threshold


def _clean_timestamp_string(value: str) -> str:
    """
    Normalise vendor-specific datetime strings so pd.to_datetime can parse them.

    Handles formats like '2026-04-18 12:32:02,623000us' (comma-fractional with
    'us' suffix) by replacing the comma with a dot and stripping the 'us'
    trailer. Plain ISO strings pass through unchanged.
    """
    if value is None:
        return ""
    s = str(value).strip()
    # Strip trailing microsecond unit if present
    if s.endswith("us") or s.endswith("US"):
        s = s[:-2].rstrip()
    # If the seconds use a comma as decimal separator, swap to a dot
    # (only if there is exactly one comma and no dot in the time portion).
    if "," in s and "." not in s.rsplit(":", 1)[-1]:
        s = s.replace(",", ".", 1)
    return s


def _detect_timestamp_column(df: pd.DataFrame) -> str | None:
    """Return the name of the column to use as Timestamp, or None."""
    # 1. Already-typed datetime column
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return col

    # 2. Strong-hint name match (datetime / timestamp etc.)
    for col in df.columns:
        cn = str(col).strip().lower()
        if any(hint in cn for hint in _STRONG_TS_HINTS):
            return col

    # 3. Weak-hint match (date / time) WHERE values actually parse as datetimes
    for col in df.columns:
        cn = str(col).strip().lower()
        if any(hint in cn for hint in _WEAK_TS_HINTS):
            if _values_parse_as_datetime(df[col].head(50)):
                return col

    # 4. Last resort: first column whose values mostly parse as datetimes
    for col in df.columns:
        if _values_parse_as_datetime(df[col].head(50), threshold=0.8):
            return col

    return None


def _read_xls_or_xlsx(path: str) -> pd.DataFrame:
    """
    Read an XLS/XLSX recording into a raw DataFrame.

    Uses python_calamine (already a project dependency via WinScope) which is
    far more tolerant of vendor-exported XLS quirks than xlrd. Picks the first
    sheet that contains at least a header row plus one data row.
    """
    from python_calamine import CalamineWorkbook

    wb = CalamineWorkbook.from_path(str(path))
    chosen_sheet = None
    chosen_rows: list = []
    for sheet_name in wb.sheet_names:
        rows = wb.get_sheet_by_name(sheet_name).to_python()
        if rows and len(rows) >= 2 and any(v not in (None, "") for v in rows[0]):
            chosen_sheet = sheet_name
            chosen_rows = rows
            break

    if not chosen_sheet:
        raise ValueError(
            "No sheet with a header row plus data was found. The file may be "
            "empty or in an unexpected layout."
        )

    header = [str(c).strip() if c is not None else "" for c in chosen_rows[0]]
    data = [r for r in chosen_rows[1:] if any(v not in (None, "") for v in r)]
    df = pd.DataFrame(data, columns=header)
    # Drop empty / unnamed columns left over from sparse exports
    df = df.loc[:, [c for c in df.columns if c]]
    return df


def load_ecu_recording(path: str) -> pd.DataFrame:
    """
    Read an ECU recording XLS/XLSX into a normalised DataFrame.

    - Reads the first non-empty sheet via python_calamine.
    - Auto-detects a timestamp column (strong hints first, then weak hints
      backed by datetime parseability) and renames it to "Timestamp".
    - Vendor-specific datetime strings (comma-fractional seconds, 'us'
      suffix) are normalised before parsing.
    - Coerces every other column to numeric; drops columns that are
      entirely NaN after coercion (i.e. text-only columns).
    - Sorts by Timestamp (stable mergesort) and drops rows with NaT
      timestamps.

    Raises ValueError if no timestamp column can be identified or no
    numeric channels remain.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"ECU recording not found: {path}")

    ext = os.path.splitext(path)[1].lower()
    if ext not in (".xls", ".xlsx"):
        raise ValueError(f"Unsupported ECU recording extension: {ext}")

    df = _read_xls_or_xlsx(path)

    ts_col = _detect_timestamp_column(df)
    if ts_col is None:
        raise ValueError(
            "Could not identify a timestamp column. Expected a column named "
            "Timestamp / Time / Date / DateTime, or one whose values parse "
            "as datetimes."
        )

    if ts_col != "Timestamp":
        df = df.rename(columns={ts_col: "Timestamp"})

    if not pd.api.types.is_datetime64_any_dtype(df["Timestamp"]):
        df["Timestamp"] = pd.to_datetime(
            df["Timestamp"].astype(str).map(_clean_timestamp_string),
            errors="coerce",
        )

    channels: list[str] = []
    for col in [c for c in df.columns if c != "Timestamp"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if df[col].notna().any():
            channels.append(col)
        else:
            df = df.drop(columns=[col])

    if not channels:
        raise ValueError("No numeric channels found in the ECU recording.")

    df = df.dropna(subset=["Timestamp"])
    df = df.sort_values("Timestamp", kind="mergesort").reset_index(drop=True)

    return df[["Timestamp"] + channels]


def _tidy_channel_label(name: str) -> str:
    """
    Produce a human-readable label from raw vendor channel names like
    '1__1_1005_012_Engine_Power_§kW'.

    - Splits on the section sign (§) to separate the parameter name from
      its unit.
    - Strips a leading numeric/underscore prefix (e.g. '1__1_1005_012_').
    - Replaces remaining underscores with spaces.
    - Re-attaches the unit in brackets, if present.

    Returns the original name unchanged if no transformation rules apply.
    """
    raw = str(name)
    if "§" not in raw:
        return raw
    body, _, unit = raw.partition("§")
    body = body.rstrip("_").strip()
    body = re.sub(r"^[\d_]+", "", body).strip("_")
    body = body.replace("_", " ").strip()
    body = re.sub(r"\s+", " ", body)
    unit = unit.strip()
    if not body:
        return raw
    return f"{body} ({unit})" if unit else body


def classify_columns(columns: list[str]) -> dict[str, list[str]]:
    """
    Group columns by keyword match against their lowercased names.

    Returns an ordered dict of {group_name: [columns]}. Only groups that
    received at least one column are present. "Other" is appended last
    if any column matched nothing.
    """
    buckets: dict[str, list[str]] = {g: [] for g, _ in _GROUP_KEYWORDS}
    other: list[str] = []

    for col in columns:
        cn = str(col).lower()
        matched = False
        for group, kws in _GROUP_KEYWORDS:
            if any(kw in cn for kw in kws):
                buckets[group].append(col)
                matched = True
                break
        if not matched:
            other.append(col)

    result = {g: cols for g, cols in buckets.items() if cols}
    if other:
        result["Other"] = other
    return result


def slugify_group_name(name: str) -> str:
    """Filesystem-safe slug for plot filenames."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
    return s or "group"
