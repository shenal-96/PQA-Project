"""Parse ComAp CSV configuration files into structured dicts."""

import pandas as pd
from pathlib import Path
from typing import Dict, Any


def parse_csv_file(filepath: str) -> Dict[str, Any]:
    """Load and parse a ComAp CSV configuration file.

    Returns dict with 'label' and 'data' (flat structure with all parameters).
    """
    label = Path(filepath).stem

    try:
        # Read CSV with semicolon delimiter, skipping first few rows
        df = pd.read_csv(filepath, sep=";", skiprows=4, dtype=str)
    except Exception as e:
        raise ValueError(f"Could not read CSV file {filepath}: {str(e)}")

    # Clean up column names (remove extra spaces)
    df.columns = df.columns.str.strip()

    # Build a hierarchical key: Group > Sub-group > Name
    data = {}

    for idx, row in df.iterrows():
        try:
            group = str(row.get("Group", "")).strip() if pd.notna(row.get("Group")) else ""
            sub_group = str(row.get("Sub-group", "")).strip() if pd.notna(row.get("Sub-group")) else ""
            name = str(row.get("Name", "")).strip() if pd.notna(row.get("Name")) else ""
            value = row.get("Value", "")
            dimension = str(row.get("Dimension", "")).strip() if pd.notna(row.get("Dimension")) else ""

            # Skip empty rows
            if not name or name == "":
                continue

            # Skip header rows (lines with only group/sub-group but no name)
            if not value or (pd.isna(value) and sub_group == ""):
                continue

            # Create hierarchical key
            key = f"{group}|{sub_group}|{name}"

            # Try to convert value to numeric if possible
            try:
                numeric_value = float(value)
            except (ValueError, TypeError):
                numeric_value = None

            data[key] = {
                "group": group,
                "sub_group": sub_group,
                "name": name,
                "value": value,
                "numeric_value": numeric_value,
                "dimension": dimension,
            }
        except Exception:
            continue

    return {"label": label, "data": data, "type": "csv"}
