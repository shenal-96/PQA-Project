"""Compare CSV configuration files."""

from typing import Dict, List, Any


def compare_csv_files(files: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compare multiple CSV files. For each parameter with differences, show all values.

    Returns list of difference locations with all file values.
    """
    diffs = []

    # Get list of file labels
    file_labels = [label for label in files.keys() if files[label].get("type") == "csv"]

    if not file_labels:
        return []

    # Get all shared keys across files
    all_keys = None
    for label in file_labels:
        data = files[label].get("data", {})
        keys = set(data.keys())
        if all_keys is None:
            all_keys = keys
        else:
            all_keys &= keys

    if not all_keys:
        return []

    # For each key, check if values differ across files
    for key in sorted(all_keys):
        values = {}
        numeric_values = {}
        group = None
        sub_group = None
        name = None
        dimension = None

        for label in file_labels:
            data = files[label].get("data", {})
            param = data.get(key, {})
            values[label] = param.get("value", "")
            numeric_values[label] = param.get("numeric_value")

            if group is None:
                group = param.get("group", "")
                sub_group = param.get("sub_group", "")
                name = param.get("name", "")
                dimension = param.get("dimension", "")

        # Check if values differ (compare both string and numeric)
        string_values = set(v for v in values.values() if v != "")
        numeric_vals = set(v for v in numeric_values.values() if v is not None)

        # If there are differences in either string or numeric values
        has_string_diff = len(string_values) > 1
        has_numeric_diff = len(numeric_vals) > 1

        if has_string_diff or has_numeric_diff:
            diff_row = {
                "Group": group,
                "Sub-group": sub_group,
                "Name": name,
                "Dimension": dimension,
            }
            diff_row.update(values)
            diffs.append(diff_row)

    return diffs
