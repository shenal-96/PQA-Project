"""Parse ECU parameter .XLS files into structured dicts."""

import pandas as pd
from pathlib import Path
from typing import Dict, Any


def parse_file(filepath: str) -> Dict[str, Any]:
    """Load and parse a single XLS/XLSX file using pandas.

    Returns dict with 'label' and 'sheets' (containing Parameter, Val_2D, Val_3D).
    """
    label = Path(filepath).stem
    sheets = {}

    try:
        excel_file = pd.ExcelFile(filepath)
    except Exception as e:
        raise ValueError(f"Could not read file {filepath}: {str(e)}")

    for sheet_name in excel_file.sheet_names:
        if sheet_name == "Parameter":
            sheets["Parameter"] = parse_parameter(filepath, sheet_name)
        elif sheet_name == "Val_2D":
            sheets["Val_2D"] = parse_val_2d(filepath, sheet_name)
        elif sheet_name == "Val_3D":
            sheets["Val_3D"] = parse_val_3d(filepath, sheet_name)

    return {"label": label, "sheets": sheets}


def parse_parameter(filepath: str, sheet_name: str) -> Dict[str, Dict[str, Any]]:
    """Parse Parameter sheet: Nr -> {name, value, unit}."""
    df = pd.read_excel(filepath, sheet_name=sheet_name, header=None)

    result = {}

    for idx, row in df.iterrows():
        try:
            nr = row.iloc[0]
            if pd.isna(nr):
                continue

            name = row.iloc[1] if len(row) > 1 else ""
            value = row.iloc[2] if len(row) > 2 else None
            unit = row.iloc[3] if len(row) > 3 else ""

            try:
                value = float(value) if pd.notna(value) else None
            except (ValueError, TypeError):
                value = None

            nr_key = str(int(nr) if isinstance(nr, float) else nr)
            result[nr_key] = {
                "name": str(name) if pd.notna(name) else "",
                "value": value,
                "unit": str(unit) if pd.notna(unit) else "",
            }
        except Exception:
            continue

    return result


def parse_val_2d(filepath: str, sheet_name: str) -> Dict[str, Dict[str, Any]]:
    """Parse Val_2D sheet. Each curve = 4 rows: [id, x-axis, y-axis, blank]."""
    df = pd.read_excel(filepath, sheet_name=sheet_name, header=None)
    rows = df.values.tolist()

    result = {}
    row_idx = 0

    while row_idx < len(rows):
        try:
            nr = rows[row_idx][0]
            if pd.isna(nr):
                row_idx += 1
                continue

            name = rows[row_idx][1] if len(rows[row_idx]) > 1 else ""
            nr_key = str(int(nr) if isinstance(nr, float) else nr)

            if row_idx + 2 >= len(rows):
                row_idx += 4
                continue

            x_row = rows[row_idx + 1]
            y_row = rows[row_idx + 2]

            x_values = []
            y_values = []

            for col in range(2, len(x_row)):
                x_val = x_row[col]
                y_val = y_row[col]

                try:
                    x_values.append(float(x_val) if pd.notna(x_val) else 0)
                    y_values.append(float(y_val) if pd.notna(y_val) else 0)
                except (ValueError, TypeError):
                    pass

            result[nr_key] = {
                "name": str(name) if pd.notna(name) else "",
                "x_values": x_values,
                "y_values": y_values,
            }

            row_idx += 4
        except Exception:
            row_idx += 4

    return result


def parse_val_3d(filepath: str, sheet_name: str) -> Dict[str, Dict[str, Any]]:
    """Parse Val_3D sheet. Each map = variable rows: [id+x, data rows..., blank]."""
    df = pd.read_excel(filepath, sheet_name=sheet_name, header=None)
    rows = df.values.tolist()

    result = {}
    row_idx = 0

    while row_idx < len(rows):
        try:
            nr = rows[row_idx][0]
            if pd.isna(nr):
                row_idx += 1
                continue

            # Skip rows without a numeric Nr (floating point number)
            if not isinstance(nr, (int, float)):
                row_idx += 1
                continue

            name = rows[row_idx][1] if len(rows[row_idx]) > 1 else ""
            nr_key = str(int(nr))

            # X-axis values start at column F (index 5) of the identifier row
            x_values = []
            for col in range(5, len(rows[row_idx])):
                x_val = rows[row_idx][col]
                if pd.isna(x_val) or x_val == "":
                    break
                try:
                    x_values.append(float(x_val))
                except (ValueError, TypeError):
                    break

            y_values = []
            grid = []
            data_row = row_idx + 1

            # Parse data rows until we hit a separator
            while data_row < len(rows):
                # Column E (index 4) contains y-axis breakpoints in data rows
                y_val = rows[data_row][4] if len(rows[data_row]) > 4 else None
                col_c = rows[data_row][2] if len(rows[data_row]) > 2 else None

                # Empty row = separator between maps
                if (pd.isna(y_val) or y_val == "") and (pd.isna(col_c) or col_c == ""):
                    break

                # Skip "rpm" header row
                if isinstance(col_c, str) and col_c.lower() == "rpm":
                    data_row += 1
                    continue

                # Parse y-axis value (must be numeric)
                if pd.isna(y_val):
                    data_row += 1
                    continue

                try:
                    y_num = float(y_val)
                except (ValueError, TypeError):
                    data_row += 1
                    continue

                y_values.append(y_num)

                # Grid values start at column F (index 5) matching x-axis column positions
                row_values = []
                for col in range(5, 5 + len(x_values)):
                    if col >= len(rows[data_row]):
                        break
                    cell_val = rows[data_row][col]
                    try:
                        row_values.append(float(cell_val) if pd.notna(cell_val) and cell_val != "" else 0)
                    except (ValueError, TypeError):
                        row_values.append(0)

                if row_values:
                    grid.append(row_values)

                data_row += 1

            result[nr_key] = {
                "name": str(name) if pd.notna(name) else "",
                "x_values": x_values,
                "y_values": y_values,
                "grid": grid,
            }

            row_idx = data_row + 1
        except Exception:
            row_idx += 1

    return result
