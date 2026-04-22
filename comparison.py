"""Excel file comparison module — UI-free functions for comparing Excel files."""

import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Tuple


def load_excel_file(file_path: str) -> Dict[str, pd.DataFrame]:
    """Load all sheets from an Excel file."""
    try:
        xls = pd.ExcelFile(file_path)
        sheets = {}
        for sheet_name in xls.sheet_names:
            sheets[sheet_name] = pd.read_excel(file_path, sheet_name=sheet_name)
        return sheets
    except Exception as e:
        raise ValueError(f"Failed to load Excel file {file_path}: {str(e)}")


def compare_excel_files(file_paths: List[str]) -> List[Dict[str, Any]]:
    """
    Compare multiple Excel files and return a list of differences.

    Returns a list of dicts with keys:
    - file_name: Name of the file with difference
    - tab_name: Sheet name where difference was found
    - row_num: Row number (1-indexed)
    - column: Column name
    - value: Value in this file
    - expected_value: Value in first file (baseline)
    - row_data: The full row data for context
    """
    if not file_paths or len(file_paths) < 2:
        return []

    differences = []
    baseline_file = file_paths[0]
    baseline_sheets = load_excel_file(baseline_file)
    baseline_name = Path(baseline_file).name

    for comparison_file in file_paths[1:]:
        comparison_sheets = load_excel_file(comparison_file)
        comparison_name = Path(comparison_file).name

        # Check for sheet-level differences
        baseline_sheet_names = set(baseline_sheets.keys())
        comparison_sheet_names = set(comparison_sheets.keys())

        missing_sheets = baseline_sheet_names - comparison_sheet_names
        for sheet_name in missing_sheets:
            differences.append({
                "file_name": comparison_name,
                "tab_name": sheet_name,
                "row_num": None,
                "column": None,
                "value": "MISSING SHEET",
                "expected_value": f"Sheet exists in {baseline_name}",
                "row_data": {},
            })

        extra_sheets = comparison_sheet_names - baseline_sheet_names
        for sheet_name in extra_sheets:
            differences.append({
                "file_name": comparison_name,
                "tab_name": sheet_name,
                "row_num": None,
                "column": None,
                "value": "EXTRA SHEET",
                "expected_value": f"Does not exist in {baseline_name}",
                "row_data": {},
            })

        # Compare data in common sheets
        for sheet_name in baseline_sheet_names & comparison_sheet_names:
            baseline_df = baseline_sheets[sheet_name]
            comparison_df = comparison_sheets[sheet_name]

            # Convert to same shape for comparison
            baseline_df = baseline_df.reset_index(drop=True)
            comparison_df = comparison_df.reset_index(drop=True)

            max_rows = max(len(baseline_df), len(comparison_df))

            # Pad shorter dataframe with NaN
            if len(baseline_df) < max_rows:
                baseline_df = pd.concat(
                    [baseline_df, pd.DataFrame(index=range(len(baseline_df), max_rows))],
                    ignore_index=True
                )
            if len(comparison_df) < max_rows:
                comparison_df = pd.concat(
                    [comparison_df, pd.DataFrame(index=range(len(comparison_df), max_rows))],
                    ignore_index=True
                )

            # Compare data
            for row_idx in range(max_rows):
                baseline_row = baseline_df.iloc[row_idx] if row_idx < len(baseline_df) else None
                comparison_row = comparison_df.iloc[row_idx] if row_idx < len(comparison_df) else None

                if baseline_row is None:
                    # Extra row in comparison file
                    differences.append({
                        "file_name": comparison_name,
                        "tab_name": sheet_name,
                        "row_num": row_idx + 2,  # +2 for 1-indexed header row
                        "column": "ROW",
                        "value": "EXTRA ROW",
                        "expected_value": f"Row does not exist in {baseline_name}",
                        "row_data": comparison_row.to_dict() if comparison_row is not None else {},
                    })
                    continue

                if comparison_row is None:
                    # Missing row in comparison file
                    differences.append({
                        "file_name": comparison_name,
                        "tab_name": sheet_name,
                        "row_num": row_idx + 2,
                        "column": "ROW",
                        "value": "MISSING ROW",
                        "expected_value": f"Row exists in {baseline_name}",
                        "row_data": baseline_row.to_dict(),
                    })
                    continue

                # Compare cell values
                for col in baseline_df.columns:
                    if col not in comparison_df.columns:
                        differences.append({
                            "file_name": comparison_name,
                            "tab_name": sheet_name,
                            "row_num": row_idx + 2,
                            "column": col,
                            "value": "MISSING COLUMN",
                            "expected_value": f"Column exists in {baseline_name}",
                            "row_data": comparison_row.to_dict(),
                        })
                    else:
                        baseline_val = baseline_row[col]
                        comparison_val = comparison_row[col]

                        # Normalize values for comparison (handle NaN, dtype differences)
                        baseline_is_na = pd.isna(baseline_val)
                        comparison_is_na = pd.isna(comparison_val)

                        if baseline_is_na and comparison_is_na:
                            continue
                        elif baseline_is_na or comparison_is_na:
                            differences.append({
                                "file_name": comparison_name,
                                "tab_name": sheet_name,
                                "row_num": row_idx + 2,
                                "column": col,
                                "value": str(comparison_val) if not comparison_is_na else "EMPTY",
                                "expected_value": str(baseline_val) if not baseline_is_na else "EMPTY",
                                "row_data": comparison_row.to_dict(),
                            })
                        elif str(baseline_val).strip() != str(comparison_val).strip():
                            differences.append({
                                "file_name": comparison_name,
                                "tab_name": sheet_name,
                                "row_num": row_idx + 2,
                                "column": col,
                                "value": str(comparison_val),
                                "expected_value": str(baseline_val),
                                "row_data": comparison_row.to_dict(),
                            })

                # Check for extra columns in comparison
                for col in comparison_df.columns:
                    if col not in baseline_df.columns:
                        differences.append({
                            "file_name": comparison_name,
                            "tab_name": sheet_name,
                            "row_num": row_idx + 2,
                            "column": col,
                            "value": str(comparison_row[col]),
                            "expected_value": "EXTRA COLUMN (not in baseline)",
                            "row_data": comparison_row.to_dict(),
                        })

    return differences


def format_differences_for_display(differences: List[Dict[str, Any]]) -> pd.DataFrame:
    """Convert differences list to a displayable DataFrame."""
    if not differences:
        return pd.DataFrame(columns=["File", "Tab", "Row", "Column", "Found", "Expected"])

    display_data = []
    for diff in differences:
        display_data.append({
            "File": diff["file_name"],
            "Tab": diff["tab_name"],
            "Row": diff["row_num"] if diff["row_num"] is not None else "—",
            "Column": diff["column"] if diff["column"] is not None else "—",
            "Found": diff["value"],
            "Expected": diff["expected_value"],
        })

    return pd.DataFrame(display_data)
