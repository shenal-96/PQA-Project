"""Compare multiple files and show all values at each difference location."""

from typing import Dict, List, Any


def compare_all_files(files: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compare all files at once. For each location with any difference, show all file values.

    Returns list of difference locations with all file values.
    """
    diffs = []

    # Get list of file labels
    file_labels = list(files.keys())

    # Process Parameter sheet
    diffs.extend(compare_parameter_all(files, file_labels))

    # Process Val_2D sheet
    diffs.extend(compare_val_2d_all(files, file_labels))

    # Process Val_3D sheet
    diffs.extend(compare_val_3d_all(files, file_labels))

    return sorted(diffs, key=lambda x: (x["Sheet"], x["Nr"], x.get("Location", "")))


def compare_parameter_all(files: Dict, file_labels: List[str]) -> List[Dict[str, Any]]:
    """Compare Parameter sheet across all files."""
    diffs = []

    # Get all shared Nrs
    all_nrs = None
    for label in file_labels:
        param_sheet = files[label]["sheets"].get("Parameter", {})
        nrs = set(param_sheet.keys())
        if all_nrs is None:
            all_nrs = nrs
        else:
            all_nrs &= nrs

    if not all_nrs:
        return []

    # For each Nr, check if values differ across files
    for nr in sorted(all_nrs, key=lambda x: float(x) if x.isdigit() else 0):
        values = {}
        name = None

        for label in file_labels:
            param_sheet = files[label]["sheets"].get("Parameter", {})
            data = param_sheet.get(nr, {})
            values[label] = data.get("value")
            if name is None:
                name = data.get("name", "")

        # Check if any values differ
        unique_values = set(v for v in values.values() if v is not None)
        if len(unique_values) > 1:
            diff_row = {
                "Sheet": "Parameter",
                "Nr": nr,
                "Name": name,
                "Location": "Value",
            }
            diff_row.update(values)
            diffs.append(diff_row)

    return diffs


def compare_val_2d_all(files: Dict, file_labels: List[str]) -> List[Dict[str, Any]]:
    """Compare Val_2D sheet across all files."""
    diffs = []

    # Get all shared Nrs
    all_nrs = None
    for label in file_labels:
        val_2d = files[label]["sheets"].get("Val_2D", {})
        nrs = set(val_2d.keys())
        if all_nrs is None:
            all_nrs = nrs
        else:
            all_nrs &= nrs

    if not all_nrs:
        return []

    # For each Nr, compare y_values
    for nr in sorted(all_nrs, key=lambda x: float(x) if x.isdigit() else 0):
        y_values_all = {}
        name = None
        max_len = 0

        for label in file_labels:
            val_2d = files[label]["sheets"].get("Val_2D", {})
            data = val_2d.get(nr, {})
            y_vals = data.get("y_values", [])
            y_values_all[label] = y_vals
            max_len = max(max_len, len(y_vals))
            if name is None:
                name = data.get("name", "")

        # Check each y-value index
        for idx in range(max_len):
            values = {}
            has_diff = False
            unique_vals = set()

            for label in file_labels:
                val = y_values_all[label][idx] if idx < len(y_values_all[label]) else None
                values[label] = val
                if val is not None:
                    unique_vals.add(round(val, 9))  # Round to avoid floating point issues

            if len(unique_vals) > 1:
                diff_row = {
                    "Sheet": "Val_2D",
                    "Nr": nr,
                    "Name": name,
                    "Location": f"y[{idx}]",
                }
                diff_row.update(values)
                diffs.append(diff_row)

    return diffs


def compare_val_3d_all(files: Dict, file_labels: List[str]) -> List[Dict[str, Any]]:
    """Compare Val_3D sheet across all files."""
    diffs = []

    # Get all shared Nrs
    all_nrs = None
    for label in file_labels:
        val_3d = files[label]["sheets"].get("Val_3D", {})
        nrs = set(val_3d.keys())
        if all_nrs is None:
            all_nrs = nrs
        else:
            all_nrs &= nrs

    if not all_nrs:
        return []

    # For each Nr, compare grid values
    for nr in sorted(all_nrs, key=lambda x: float(x) if x.isdigit() else 0):
        grids = {}
        name = None
        max_rows = 0
        max_cols = 0

        for label in file_labels:
            val_3d = files[label]["sheets"].get("Val_3D", {})
            data = val_3d.get(nr, {})
            grid = data.get("grid", [])
            grids[label] = grid
            if grid:
                max_rows = max(max_rows, len(grid))
                max_cols = max(max_cols, max(len(row) for row in grid) if grid else 0)
            if name is None:
                name = data.get("name", "")

        # Check each grid cell
        for row_idx in range(max_rows):
            for col_idx in range(max_cols):
                values = {}
                unique_vals = set()

                for label in file_labels:
                    grid = grids[label]
                    if row_idx < len(grid) and col_idx < len(grid[row_idx]):
                        val = grid[row_idx][col_idx]
                    else:
                        val = None
                    values[label] = val
                    if val is not None:
                        unique_vals.add(round(val, 9))

                if len(unique_vals) > 1:
                    diff_row = {
                        "Sheet": "Val_3D",
                        "Nr": nr,
                        "Name": name,
                        "Location": f"[{row_idx}][{col_idx}]",
                    }
                    diff_row.update(values)
                    diffs.append(diff_row)

    return diffs
