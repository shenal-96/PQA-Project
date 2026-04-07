"""
Core Analysis Engine for Power Quality Analysis.

Contains all data processing, event detection, and compliance checking logic.
No UI dependencies - pure data functions.
"""

import pandas as pd
import numpy as np
import warnings
from dataclasses import dataclass


@dataclass
class AnalysisConfig:
    """All configurable parameters for the analysis."""
    nominal_voltage: float = 415.0
    nominal_frequency: float = 50.0
    load_threshold_kw: float = 50.0
    voltage_tolerance_pct: float = 1.0
    voltage_recovery_time_s: float = 4.0
    voltage_max_deviation_pct: float = 15.0
    frequency_tolerance_pct: float = 0.5
    frequency_recovery_time_s: float = 3.0
    frequency_max_deviation_pct: float = 7.0

    @classmethod
    def iso_8528_defaults(cls):
        """Return config with ISO 8528 standard values."""
        return cls(
            load_threshold_kw=50.0,
            voltage_tolerance_pct=1.0,
            voltage_recovery_time_s=4.0,
            voltage_max_deviation_pct=15.0,
            frequency_tolerance_pct=0.5,
            frequency_recovery_time_s=3.0,
            frequency_max_deviation_pct=7.0,
        )


def robust_to_datetime(series):
    """Parse datetime series trying multiple formats."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, message=".*Could not infer format.*")
        for fmt in ["%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S"]:
            try:
                return pd.to_datetime(series, format=fmt, errors="raise")
            except Exception:
                continue
        return pd.to_datetime(series, dayfirst=True, errors="coerce")


def load_and_prepare_csv(file_path_or_buffer, start_time=None, end_time=None):
    """
    Load a CSV file and prepare it for analysis.

    Parameters:
        file_path_or_buffer: path string or file-like object
        start_time: optional HH:MM:SS string to filter start
        end_time: optional HH:MM:SS string to filter end

    Returns:
        tuple: (df, client_name) where df has a 'Timestamp' column
    """
    df = pd.read_csv(file_path_or_buffer, sep=None, engine="python")
    df.columns = [str(c).replace("\x00", "").replace(" (Q)", "").strip() for c in df.columns]

    # Parse timestamps from various column layouts
    if "PC Time" in df.columns:
        df["Timestamp"] = robust_to_datetime(df["PC Time"])
    elif "Date" in df.columns and "Time" in df.columns:
        df["Timestamp"] = robust_to_datetime(df["Date"] + " " + df["Time"])
    else:
        df["Timestamp"] = robust_to_datetime(df.iloc[:, 1])

    df = df.dropna(subset=["Timestamp"]).sort_values("Timestamp").reset_index(drop=True)

    # Apply time filtering
    if start_time and end_time and not df.empty:
        try:
            df_date = df["Timestamp"].dt.date.iloc[0]
            start_dt = pd.to_datetime(f"{df_date} {start_time}")
            end_dt = pd.to_datetime(f"{df_date} {end_time}")
            df = df[(df["Timestamp"] >= start_dt) & (df["Timestamp"] <= end_dt)]
        except Exception as e:
            print(f"Time filtering error: {e}")

    return df


def calculate_recovery_time(df_data, event_timestamp, metric_column, nominal_value, tolerance_percent=1.0):
    """
    Calculate how long it takes for a metric to recover to within tolerance after an event.

    Returns:
        float or None: recovery time in seconds, or None if never recovered
    """
    upper = nominal_value * (1 + tolerance_percent / 100)
    lower = nominal_value * (1 - tolerance_percent / 100)
    start_idx = df_data["Timestamp"].searchsorted(event_timestamp, side="right")
    if start_idx >= len(df_data):
        return None
    subset = df_data.iloc[start_idx:]
    recoveries = subset[(subset[metric_column] >= lower) & (subset[metric_column] <= upper)]
    if not recoveries.empty:
        return (recoveries.iloc[0]["Timestamp"] - event_timestamp).total_seconds()
    return None


def check_compliance(row, config: AnalysisConfig):
    """
    Check a single event row against compliance criteria.

    Returns:
        pd.Series with 'Compliance_Status' and 'Failure_Reasons'
    """
    reasons = []
    status = "Pass"

    nom_v = config.nominal_voltage
    nom_f = config.nominal_frequency

    # Voltage checks
    if pd.notnull(row["V_dev"]):
        v_dev_pct = (abs(row["V_dev"]) / nom_v) * 100
        if v_dev_pct > config.voltage_max_deviation_pct:
            status = "Fail"
            reasons.append(f"Voltage Dev {v_dev_pct:.1f}% > {config.voltage_max_deviation_pct}%")
        if pd.isna(row["V_rec_s"]) and v_dev_pct > config.voltage_tolerance_pct:
            status = "Fail"
            reasons.append("Voltage did not recover")
        elif row["V_rec_s"] is not None and row["V_rec_s"] > config.voltage_recovery_time_s:
            status = "Fail"
            reasons.append(f"V Recovery {row['V_rec_s']:.1f}s > {config.voltage_recovery_time_s}s")

    # Frequency checks
    f_dev_pct = (abs(row["F_dev"]) / nom_f) * 100
    if f_dev_pct > config.frequency_max_deviation_pct:
        status = "Fail"
        reasons.append(f"Freq Dev {f_dev_pct:.1f}% > {config.frequency_max_deviation_pct}%")
    if pd.isna(row["F_rec_s"]) and f_dev_pct > config.frequency_tolerance_pct:
        status = "Fail"
        reasons.append("Freq did not recover")
    elif row["F_rec_s"] is not None and row["F_rec_s"] > config.frequency_recovery_time_s:
        status = "Fail"
        reasons.append(f"F Recovery {row['F_rec_s']:.1f}s > {config.frequency_recovery_time_s}s")

    return pd.Series([status, "; ".join(reasons)], index=["Compliance_Status", "Failure_Reasons"])


def perform_analysis(df, config: AnalysisConfig):
    """
    Main analysis: process data, detect events, calculate compliance.

    Returns:
        tuple: (df_proc, df_events) - processed data and detected events with compliance
    """
    nom_v = config.nominal_voltage
    nom_f = config.nominal_frequency
    thresh_kw = config.load_threshold_kw

    df_proc = pd.DataFrame({"Timestamp": df["Timestamp"]})

    # --- Voltage ---
    v_cols_ln = ["U1_rms_AVG", "U2_rms_AVG", "U3_rms_AVG"]
    v_cols_ll = ["U12_rms_AVG", "U23_rms_AVG", "U31_rms_AVG"]

    if all(c in df.columns for c in v_cols_ln):
        raw_avg = df[v_cols_ln].apply(pd.to_numeric, errors="coerce").mean(axis=1)
        df_proc["Avg_Voltage_LL"] = raw_avg * np.sqrt(3)
    elif any(c in df.columns for c in v_cols_ll):
        existing_ll = [c for c in v_cols_ll if c in df.columns]
        df_proc["Avg_Voltage_LL"] = df[existing_ll].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    else:
        df_proc["Avg_Voltage_LL"] = np.nan

    # --- Current ---
    i_cols = ["I1_rms_AVG", "I2_rms_AVG", "I3_rms_AVG"]
    if all(c in df.columns for c in i_cols):
        df_proc["Avg_Current"] = df[i_cols].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    else:
        df_proc["Avg_Current"] = np.nan

    # --- THD ---
    thd_cols = [c for c in df.columns if "THD" in c.upper() and "AVG" in c.upper()]
    df_proc["Avg_THD_F"] = df[thd_cols].apply(pd.to_numeric, errors="coerce").mean(axis=1) if thd_cols else np.nan

    # --- Power Factor ---
    pf_cols = [c for c in df.columns if "PF" in c.upper() and "AVG" in c.upper()]
    df_proc["Avg_PF"] = df[pf_cols].apply(pd.to_numeric, errors="coerce").mean(axis=1) if pf_cols else np.nan

    # --- Power & Frequency ---
    df_proc["Avg_kW"] = pd.to_numeric(df.get("P_sum_AVG", 0), errors="coerce") / 1000
    df_proc["Avg_Frequency"] = pd.to_numeric(df.get("Freq_AVG", np.nan), errors="coerce")
    df_proc["dKw"] = df_proc["Avg_kW"].diff().fillna(0)

    # --- Event Detection ---
    raw_events = df_proc[df_proc["dKw"].abs() > float(thresh_kw)].copy()
    grouped_events = []
    if not raw_events.empty:
        curr = None
        for _, row in raw_events.iterrows():
            if curr is None:
                curr = row.to_dict()
                curr["Start_Timestamp"] = row["Timestamp"]
                curr["End_Timestamp"] = row["Timestamp"]
                curr["Total_dKw"] = row["dKw"]
            else:
                if (row["Timestamp"] - curr["Timestamp"]).total_seconds() <= 5:
                    curr["Total_dKw"] += row["dKw"]
                    curr["Timestamp"] = row["Timestamp"]
                    curr["End_Timestamp"] = row["Timestamp"]
                else:
                    grouped_events.append(curr)
                    curr = row.to_dict()
                    curr["Start_Timestamp"] = row["Timestamp"]
                    curr["End_Timestamp"] = row["Timestamp"]
                    curr["Total_dKw"] = row["dKw"]
        if curr:
            grouped_events.append(curr)

    events = pd.DataFrame(grouped_events)

    if not events.empty:
        events["dKw_abs"] = events["Total_dKw"].abs()
        events["dKw"] = events["Total_dKw"]
        events["Timestamp"] = events["Start_Timestamp"]

    # --- Interpolation for recovery time calculation ---
    num_cols = df_proc.select_dtypes(include=[np.number]).columns
    df_interp = df_proc.set_index("Timestamp")[num_cols].resample("100ms").mean().interpolate().reset_index()

    # --- Recovery times & compliance ---
    if not events.empty:
        events["V_dev"] = events["Avg_Voltage_LL"] - nom_v
        events["F_dev"] = events["Avg_Frequency"] - nom_f

        tol_v = config.voltage_tolerance_pct
        tol_f = config.frequency_tolerance_pct

        if "Avg_Voltage_LL" in df_interp.columns and df_interp["Avg_Voltage_LL"].notna().any():
            events["V_rec_s"] = events["Timestamp"].apply(
                lambda x: calculate_recovery_time(df_interp, x, "Avg_Voltage_LL", nom_v, tol_v)
            )
        else:
            events["V_rec_s"] = np.nan

        events["F_rec_s"] = events["Timestamp"].apply(
            lambda x: calculate_recovery_time(df_interp, x, "Avg_Frequency", nom_f, tol_f)
        )

        # Apply compliance check to each event
        compliance = events.apply(lambda row: check_compliance(row, config), axis=1)
        events = pd.concat([events, compliance], axis=1)

    return df_proc, events
