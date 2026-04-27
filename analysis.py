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
    detection_window_s: float = 5.0
    # Seconds either side of each event used for snapshots AND peak-deviation lookup.
    # Increase if the generator response is slow and the nadir falls outside the window.
    snapshot_window_s: float = 10.0
    # How to interpret voltage columns from the CSV:
    #   "auto"     — detect by column names (U1/U2/U3 = L-N, U12/U23/U31 = L-L)
    #   "force_ll" — treat whatever columns are found as L-L (no scaling)
    #   "force_ln" — treat whatever columns are found as L-N (multiply by √3)
    ln_to_ll_mode: str = "auto"
    # Asymmetric frequency recovery bands (absolute Hz).
    # Load increase: generator slows → frequency drops → lower band matters more.
    # Load decrease: generator speeds up → frequency rises → upper band matters more.
    freq_recovery_upper_increase: float = 50.50
    freq_recovery_lower_increase: float = 49.75
    freq_recovery_upper_decrease: float = 50.25
    freq_recovery_lower_decrease: float = 49.50
    # After a sustained in-band window is found, keep verifying for this many
    # seconds.  If the signal exits the band again during verification
    # (oscillation), the candidate is discarded and the search resumes.
    recovery_verify_s: float = 6.0
    # When True, skip 100ms resampling and use raw data directly as df_interp.
    # Use for high-frequency sources (e.g. WinScope ~200ms) that don't need upsampling.
    skip_interpolation: bool = False

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
            freq_recovery_upper_increase=50.50,
            freq_recovery_lower_increase=49.75,
            freq_recovery_upper_decrease=50.25,
            freq_recovery_lower_decrease=49.50,
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
    df.columns = [str(c).replace("\ufeff", "").replace("\x00", "").replace(" (Q)", "").strip() for c in df.columns]

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


def validate_csv_format(df):
    """
    Validate CSV format and required columns.

    Returns:
        tuple: (is_valid: bool, errors: list of error messages, warnings: list of warning messages)
    """
    errors = []
    warnings = []

    # Check timestamp
    if "Timestamp" not in df.columns:
        errors.append("❌ Missing Timestamp column. CSV must contain 'Timestamp', 'PC Time', or 'Date'/'Time' columns.")
    elif df["Timestamp"].isna().all():
        errors.append("❌ All Timestamp values are empty or unparseable. Ensure dates are in DD/MM/YYYY format.")

    # Check voltage columns
    v_cols_ln = ["U1_rms_AVG", "U2_rms_AVG", "U3_rms_AVG"]
    v_cols_ll = ["U12_rms_AVG", "U23_rms_AVG", "U31_rms_AVG"]
    has_voltage_ll = any(c in df.columns for c in v_cols_ll)
    has_voltage_ln = all(c in df.columns for c in v_cols_ln)
    has_voltage_avg = "U_avg_AVG" in df.columns

    if not (has_voltage_ll or has_voltage_ln or has_voltage_avg):
        errors.append("❌ Missing voltage data. CSV must contain one of:\n   • U12_rms_AVG, U23_rms_AVG, U31_rms_AVG (L-L voltages)\n   • U1_rms_AVG, U2_rms_AVG, U3_rms_AVG (L-N voltages)\n   • U_avg_AVG (Average L-L voltage)")
    else:
        # Check if voltage has valid data
        voltage_cols = [c for c in df.columns if c in v_cols_ll + v_cols_ln + ["U_avg_AVG"]]
        voltage_valid = pd.to_numeric(df[voltage_cols[0]], errors="coerce").notna().any()
        if not voltage_valid:
            errors.append("❌ Voltage column is empty or contains non-numeric values.")

    # Check frequency
    if "Freq_AVG" not in df.columns:
        errors.append("❌ Missing 'Freq_AVG' (Frequency) column.")
    elif pd.to_numeric(df["Freq_AVG"], errors="coerce").isna().all():
        errors.append("❌ Frequency (Freq_AVG) column is empty or contains non-numeric values.")

    # Check power
    if "P_sum_AVG" not in df.columns:
        warnings.append("⚠️ Missing 'P_sum_AVG' (Power) column. Power calculations will not be available.")
    elif pd.to_numeric(df["P_sum_AVG"], errors="coerce").isna().all():
        errors.append("❌ Power (P_sum_AVG) column is empty or contains non-numeric values.")

    # Check current (optional but helpful)
    i_cols = ["I1_rms_AVG", "I2_rms_AVG", "I3_rms_AVG"]
    if not all(c in df.columns for c in i_cols):
        warnings.append("⚠️ Missing current columns (I1_rms_AVG, I2_rms_AVG, I3_rms_AVG). Current data unavailable.")

    # Check THD (optional)
    thd_cols = [c for c in df.columns if "THD" in c.upper() and "AVG" in c.upper()]
    if not thd_cols:
        warnings.append("⚠️ Missing THD columns. THD graphs unavailable.")

    # Check power factor (optional)
    pf_cols = [c for c in df.columns if "PF" in c.upper() and "AVG" in c.upper()]
    if not pf_cols:
        warnings.append("⚠️ Missing Power Factor columns. Power factor graphs unavailable.")

    # Check data volume
    if len(df) < 10:
        errors.append(f"❌ Insufficient data: only {len(df)} rows found. CSV must contain at least 10 data points.")

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


def load_winscope_xls(file_path_or_buffer):
    """
    Load a WinScope .xls export and return a DataFrame compatible with perform_analysis.

    Reads the 'Summary' sheet (or second sheet as fallback), strips '(Q)' suffixes,
    renames WinScope channel names to pipeline-standard column names, and converts
    the 'Generator P' column from kW → W so the pipeline's /1000 divisor is consistent.
    """
    from python_calamine import CalamineWorkbook

    wb = CalamineWorkbook.from_path(str(file_path_or_buffer))
    data_sheet = "Summary" if "Summary" in wb.sheet_names else wb.sheet_names[1]
    rows = wb.get_sheet_by_name(data_sheet).to_python()
    if not rows:
        raise ValueError(f"No data found in WinScope sheet '{data_sheet}'")

    header = [str(c).replace(" (Q)", "").strip() for c in rows[0]]
    data = [r for r in rows[1:] if any(v not in (None, "") for v in r)]
    df = pd.DataFrame(data, columns=header)

    rename_map = {
        "Generator Voltage L1-L2": "U12_rms_AVG",
        "Generator Voltage L2-L3": "U23_rms_AVG",
        "Generator Voltage L3-L1": "U31_rms_AVG",
        "Generator Current L1":    "I1_rms_AVG",
        "Generator Current L2":    "I2_rms_AVG",
        "Generator Current L3":    "I3_rms_AVG",
        "Generator Frequency":     "Freq_AVG",
        "Generator Power Factor":  "PF_sum_AVG",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # WinScope exports Generator P in kW; pipeline expects W (divides by 1000 internally)
    if "Generator P" in df.columns:
        df["P_sum_AVG"] = pd.to_numeric(df["Generator P"], errors="coerce") * 1000

    if "PC Time" in df.columns:
        df["Timestamp"] = pd.to_datetime(df["PC Time"])

    df = df.dropna(subset=["Timestamp"]).sort_values("Timestamp").reset_index(drop=True)
    return df


def calculate_recovery_time(df_interp, start_timestamp, metric_column,
                            upper, lower, sustain_s=0.3, verify_s=10.0):
    """
    Calculate recovery time using 100ms-interpolated data with exact crossing detection.

    Measures from start_timestamp (typically the band-exit crossing) to the
    moment the signal re-enters [lower, upper] and stays there stably.

    Algorithm:
    1. Scan the 100ms grid for a grid point that begins a sustained in-band
       window (sustain_s seconds of consecutive in-band points).
    2. Record that crossing as a *candidate* recovery — do NOT return yet.
    3. Continue scanning for verify_s seconds after the candidate: if the
       signal exits the band again, invalidate and search for the next
       sustained re-entry. This handles oscillating waveforms that briefly
       re-enter the band before the final settlement.
    4. Once a candidate survives verify_s of continuous in-band data, or the
       data ends while the candidate is still valid, return it.

    Parameters:
        upper / lower: absolute band boundaries in signal units (V or Hz).
        verify_s: seconds to keep verifying after a candidate is found (default 10).

    Returns:
        float or None: recovery time in seconds (to ~1ms precision), or None
    """
    subset = df_interp[df_interp["Timestamp"] > start_timestamp].reset_index(drop=True)
    if subset.empty or metric_column not in subset.columns:
        return None

    values = pd.to_numeric(subset[metric_column], errors="coerce").values
    timestamps = subset["Timestamp"].values
    within = (values >= lower) & (values <= upper)

    sustain_pts = max(1, int(sustain_s / 0.1))  # 0.1s = 100ms interval
    verify_pts = max(1, int(verify_s / 0.1))

    candidate_time = None
    candidate_idx = None  # grid index where the candidate was set

    for i in range(len(within)):
        if not within[i]:
            # Signal is out of band — invalidate any candidate
            candidate_time = None
            candidate_idx = None
            continue

        if candidate_time is not None:
            # Candidate exists and signal still in band.
            # If we've verified for verify_s past the candidate, accept it.
            if (i - candidate_idx) >= verify_pts:
                return candidate_time
            continue

        # No candidate yet — check if this starts a sustained window
        end = min(i + sustain_pts, len(within))
        if not np.all(within[i:end]):
            continue

        # Sustained in-band window starts at grid point i.
        # Interpolate back to find the exact band-crossing time between
        # grid point i-1 (out-of-band) and grid point i (in-band).
        if i == 0:
            candidate_time = (pd.Timestamp(timestamps[0]) - start_timestamp).total_seconds()
            candidate_idx = i
            continue

        v_prev = values[i - 1]
        v_curr = values[i]
        t_prev = pd.Timestamp(timestamps[i - 1])
        t_curr = pd.Timestamp(timestamps[i])
        dt = (t_curr - t_prev).total_seconds()

        if v_curr >= lower and v_prev < lower:
            boundary = lower
        elif v_curr <= upper and v_prev > upper:
            boundary = upper
        else:
            boundary = lower if abs(v_curr - lower) < abs(v_curr - upper) else upper

        dv = v_curr - v_prev
        frac = np.clip((boundary - v_prev) / dv, 0.0, 1.0) if abs(dv) > 1e-12 else 0.0
        t_cross = t_prev + pd.Timedelta(seconds=dt * frac)
        candidate_time = (t_cross - start_timestamp).total_seconds()
        candidate_idx = i

    # Data ended — return candidate if one survived to the end
    return candidate_time


def calculate_exit_time(df_interp, event_timestamp, metric_column,
                        upper, lower, lookback_s=30):
    """
    Find the exact time the signal exited the tolerance band prior to (or at)
    event_timestamp, using linear interpolation for sub-100ms precision.

    Scans backwards through the 100ms interpolated data starting from
    event_timestamp. The first in-band point found (moving backwards) marks
    the transition: that point is in-band, the next point (forward in time)
    is out-of-band. We interpolate between them to find the exact crossing.

    Edge case — signal already out of band at event time (not recovered from
    a previous event): returns event_timestamp itself so that recovery is
    measured from this event rather than inheriting stale timing from an
    earlier event.

    Parameters:
        upper / lower: absolute band boundaries in signal units (V or Hz).

    Returns:
        pd.Timestamp: exact exit time, or None if the signal never left the band
        in the lookback window (no voltage/frequency event occurred).
    """
    lookback_start = event_timestamp - pd.Timedelta(seconds=lookback_s)
    subset = df_interp[
        (df_interp["Timestamp"] >= lookback_start) &
        (df_interp["Timestamp"] <= event_timestamp)
    ].reset_index(drop=True)

    if subset.empty or metric_column not in subset.columns:
        return None

    values = pd.to_numeric(subset[metric_column], errors="coerce").values
    timestamps = subset["Timestamp"].values
    within = (values >= lower) & (values <= upper)

    # Scan backwards from the most recent point before the event
    n = len(within)
    for i in range(n - 1, -1, -1):
        if within[i]:
            # Point i is in-band. If it's the last point, the signal was
            # still in-band right up to the event — no exit detected.
            if i == n - 1:
                return None

            # Point i+1 is the first out-of-band point going forward.
            # Interpolate between i (in-band) and i+1 (out-of-band).
            v_in  = values[i]
            v_out = values[i + 1]
            t_in  = pd.Timestamp(timestamps[i])
            t_out = pd.Timestamp(timestamps[i + 1])
            dt = (t_out - t_in).total_seconds()

            # Which boundary did the signal cross through?
            if v_out > upper:
                boundary = upper
            elif v_out < lower:
                boundary = lower
            else:
                boundary = upper if abs(v_out - upper) < abs(v_out - lower) else upper

            dv = v_out - v_in
            frac = np.clip((boundary - v_in) / dv, 0.0, 1.0) if abs(dv) > 1e-12 else 0.0
            return t_in + pd.Timedelta(seconds=dt * frac)

    # Signal was out of band for the entire lookback window — can't find exit
    return None


def calculate_forward_exit_time(df_interp, event_timestamp, metric_column,
                                upper, lower, lookforward_s=30):
    """
    Find the exact time the signal exits the tolerance band AFTER event_timestamp.

    Used as a fallback when calculate_exit_time returns None — i.e. the signal
    was still in-band at the event detection point and the band exit happens
    after the load change (typical for slow governor response where the
    frequency nadir lags the load step by one or more seconds).

    Only called when the measured deviation (V_dev / F_dev) confirms the signal
    actually left the band — so this scan will always find a crossing within
    the lookforward window.

    Parameters:
        upper / lower: absolute band boundaries in signal units (V or Hz).
        lookforward_s: how far ahead to scan (default 30s).

    Returns:
        pd.Timestamp: exact exit crossing, or None if signal stayed in-band.
    """
    lookforward_end = event_timestamp + pd.Timedelta(seconds=lookforward_s)
    subset = df_interp[
        (df_interp["Timestamp"] >= event_timestamp) &
        (df_interp["Timestamp"] <= lookforward_end)
    ].reset_index(drop=True)

    if subset.empty or metric_column not in subset.columns:
        return None

    values = pd.to_numeric(subset[metric_column], errors="coerce").values
    timestamps = subset["Timestamp"].values
    within = (values >= lower) & (values <= upper)

    for i in range(len(within)):
        if not within[i]:
            # Already out of band at the event timestamp itself.
            if i == 0:
                return event_timestamp
            # Interpolate between i-1 (in-band) and i (out-of-band).
            v_in  = values[i - 1]
            v_out = values[i]
            t_in  = pd.Timestamp(timestamps[i - 1])
            t_out = pd.Timestamp(timestamps[i])
            dt    = (t_out - t_in).total_seconds()

            if v_out > upper:
                boundary = upper
            elif v_out < lower:
                boundary = lower
            else:
                boundary = upper if abs(v_out - upper) < abs(v_out - lower) else lower

            dv = v_out - v_in
            frac = np.clip((boundary - v_in) / dv, 0.0, 1.0) if abs(dv) > 1e-12 else 0.0
            return t_in + pd.Timedelta(seconds=dt * frac)

    return None  # Signal stayed in-band throughout the forward window


def _measured_extreme(df, event_ts, column, dkw, window_s=5):
    """
    Return the actual measured extreme value of `column` in the `window_s`
    seconds after event_ts, chosen by load direction:
      - Load increase (dKw > 0): frequency/voltage drops → return min value
      - Load decrease (dKw <= 0): frequency/voltage rises → return max value

    Returns the raw measured value (e.g. Volts or Hz), not a deviation.
    Pass df_proc for measured-only values.
    """
    end_ts = event_ts + pd.Timedelta(seconds=window_s)
    subset = df[
        (df["Timestamp"] >= event_ts) &
        (df["Timestamp"] <= end_ts)
    ]
    if subset.empty or column not in subset.columns:
        return np.nan
    vals = pd.to_numeric(subset[column], errors="coerce").dropna()
    if vals.empty:
        return np.nan
    return vals.min() if dkw > 0 else vals.max()


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

    # Voltage checks — V_dev is the actual measured value (V), not a signed deviation
    if pd.notnull(row["V_dev"]):
        v_dev_pct = (abs(row["V_dev"] - nom_v) / nom_v) * 100
        if v_dev_pct > config.voltage_max_deviation_pct:
            status = "Fail"
            reasons.append(f"Voltage Dev {v_dev_pct:.1f}% > {config.voltage_max_deviation_pct}%")
        # Only check recovery if voltage actually left the tolerance band.
        # V_exit_ts is None when the signal stayed in-band throughout the event.
        v_exited = pd.notnull(row.get("V_exit_ts"))
        if v_exited:
            if pd.isna(row["V_rec_s"]):
                status = "Fail"
                reasons.append("Voltage did not recover")
            elif row["V_rec_s"] > config.voltage_recovery_time_s:
                status = "Fail"
                reasons.append(f"V Recovery {row['V_rec_s']:.1f}s > {config.voltage_recovery_time_s}s")

    # Frequency checks — F_dev is the actual measured value (Hz), not a signed deviation
    f_dev_pct = (abs(row["F_dev"] - nom_f) / nom_f) * 100
    if f_dev_pct > config.frequency_max_deviation_pct:
        status = "Fail"
        reasons.append(f"Freq Dev {f_dev_pct:.1f}% > {config.frequency_max_deviation_pct}%")
    # Only check recovery if frequency actually left the tolerance band.
    f_exited = pd.notnull(row.get("F_exit_ts"))
    if f_exited:
        if pd.isna(row["F_rec_s"]):
            status = "Fail"
            reasons.append("Freq did not recover")
        elif row["F_rec_s"] > config.frequency_recovery_time_s:
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
    mode = config.ln_to_ll_mode  # "auto", "force_ll", "force_ln"

    def _read_any_v_cols(df):
        """Return averaged voltage series from whichever columns exist (no scaling)."""
        if any(c in df.columns for c in v_cols_ll):
            cols = [c for c in v_cols_ll if c in df.columns]
            return df[cols].apply(pd.to_numeric, errors="coerce").mean(axis=1)
        if all(c in df.columns for c in v_cols_ln):
            return df[v_cols_ln].apply(pd.to_numeric, errors="coerce").mean(axis=1)
        if "U_avg_AVG" in df.columns:
            return pd.to_numeric(df["U_avg_AVG"], errors="coerce")
        return pd.Series(np.nan, index=df.index)

    if mode == "force_ln":
        # User says CSV has L-N values — multiply by √3 to get L-L regardless of column names.
        df_proc["Avg_Voltage_LL"] = _read_any_v_cols(df) * np.sqrt(3)
    elif mode == "force_ll":
        # User says CSV has L-L values — use directly with no conversion.
        df_proc["Avg_Voltage_LL"] = _read_any_v_cols(df)
    else:
        # Auto-detect: L-N column names → scale by √3; L-L column names → use as-is.
        if all(c in df.columns for c in v_cols_ln):
            raw_avg = df[v_cols_ln].apply(pd.to_numeric, errors="coerce").mean(axis=1)
            df_proc["Avg_Voltage_LL"] = raw_avg * np.sqrt(3)
        elif any(c in df.columns for c in v_cols_ll):
            existing_ll = [c for c in v_cols_ll if c in df.columns]
            df_proc["Avg_Voltage_LL"] = df[existing_ll].apply(pd.to_numeric, errors="coerce").mean(axis=1)
        elif "U_avg_AVG" in df.columns:
            # Single pre-averaged LL voltage column (e.g. ROMP4 logger format)
            df_proc["Avg_Voltage_LL"] = pd.to_numeric(df["U_avg_AVG"], errors="coerce")
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
    # Logger records PF as negative on the source/generator side (sign convention).
    # Take abs() so the plot displays 1.0 at unity PF regardless of measurement direction.
    pf_cols = [c for c in df.columns if "PF" in c.upper() and "AVG" in c.upper()]
    df_proc["Avg_PF"] = df[pf_cols].apply(pd.to_numeric, errors="coerce").abs().mean(axis=1) if pf_cols else np.nan

    # --- Power & Frequency ---
    df_proc["Avg_kW"] = pd.to_numeric(df.get("P_sum_AVG", 0), errors="coerce") / 1000
    df_proc["Avg_Frequency"] = pd.to_numeric(df.get("Freq_AVG", np.nan), errors="coerce")
    df_proc["dKw"] = df_proc["Avg_kW"].diff().fillna(0)

    # --- Interpolation (100ms) — used only for compliance calculations ---
    # Skip when the source data is already at sub-second resolution (e.g. WinScope ~200ms).
    if config.skip_interpolation:
        df_interp = df_proc.copy()
    else:
        num_cols = df_proc.select_dtypes(include=[np.number]).columns
        df_interp = (
            df_proc.set_index("Timestamp")[num_cols]
            .resample("100ms")
            .mean()
            .interpolate(method="linear")
            .reset_index()
        )

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
                if (row["Timestamp"] - curr["Timestamp"]).total_seconds() <= config.detection_window_s:
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

    # --- Recovery times & compliance (all from interpolated data) ---
    if not events.empty:
        tol_v = config.voltage_tolerance_pct
        tol_f = config.frequency_tolerance_pct

        # Peak deviations — maximum absolute excursion from nominal in the
        # 30s window after each event, measured on the 100ms interpolated series.
        # Voltage band (symmetric percentage)
        v_upper = nom_v * (1 + tol_v / 100)
        v_lower = nom_v * (1 - tol_v / 100)

        if "Avg_Voltage_LL" in df_interp.columns and df_interp["Avg_Voltage_LL"].notna().any():
            # Compute V_dev first so we can gate the forward scan on it.
            events["V_dev"] = events.apply(
                lambda row: _measured_extreme(df_proc, row["Timestamp"], "Avg_Voltage_LL",
                                              row["dKw"], window_s=config.snapshot_window_s),
                axis=1,
            )
            v_exit_vals = []
            for _, row in events.iterrows():
                ts = row["Timestamp"]
                exit_ts = calculate_exit_time(df_interp, ts, "Avg_Voltage_LL", v_upper, v_lower)
                if exit_ts is None:
                    # Only scan forward if the measured extreme actually left the band.
                    v_dev = row["V_dev"]
                    if pd.notnull(v_dev) and not (v_lower <= v_dev <= v_upper):
                        exit_ts = calculate_forward_exit_time(
                            df_interp, ts, "Avg_Voltage_LL", v_upper, v_lower,
                        )
                v_exit_vals.append(exit_ts)
            events["V_exit_ts"] = v_exit_vals

            events["V_rec_s"] = events.apply(
                lambda row: calculate_recovery_time(
                    df_interp, row["V_exit_ts"], "Avg_Voltage_LL", v_upper, v_lower,
                    verify_s=config.recovery_verify_s,
                ) if pd.notnull(row["V_exit_ts"]) else None,
                axis=1,
            )
        else:
            events["V_exit_ts"] = pd.NaT
            events["V_dev"] = np.nan
            events["V_rec_s"] = np.nan

        if "Avg_Frequency" in df_interp.columns and df_interp["Avg_Frequency"].notna().any():
            # Frequency band is asymmetric and direction-dependent.
            # Load increase (dKw > 0): freq drops → use increase band.
            # Load decrease (dKw <= 0): freq rises → use decrease band.
            def _f_band(dkw):
                if dkw > 0:
                    return (config.freq_recovery_upper_increase,
                            config.freq_recovery_lower_increase)
                return (config.freq_recovery_upper_decrease,
                        config.freq_recovery_lower_decrease)

            events["F_rec_upper"] = events["dKw"].apply(
                lambda dk: config.freq_recovery_upper_increase if dk > 0
                           else config.freq_recovery_upper_decrease
            )
            events["F_rec_lower"] = events["dKw"].apply(
                lambda dk: config.freq_recovery_lower_increase if dk > 0
                           else config.freq_recovery_lower_decrease
            )
            # Compute F_dev first so we can gate the forward scan on it.
            events["F_dev"] = events.apply(
                lambda row: _measured_extreme(df_proc, row["Timestamp"], "Avg_Frequency",
                                              row["dKw"], window_s=config.snapshot_window_s),
                axis=1,
            )
            f_exit_vals = []
            for _, row in events.iterrows():
                ts = row["Timestamp"]
                f_upper, f_lower = _f_band(row["dKw"])
                exit_ts = calculate_exit_time(df_interp, ts, "Avg_Frequency", f_upper, f_lower)
                if exit_ts is None:
                    # Only scan forward if the measured extreme actually left the band.
                    f_dev = row["F_dev"]
                    if pd.notnull(f_dev) and not (f_lower <= f_dev <= f_upper):
                        exit_ts = calculate_forward_exit_time(
                            df_interp, ts, "Avg_Frequency", f_upper, f_lower,
                        )
                f_exit_vals.append(exit_ts)
            events["F_exit_ts"] = f_exit_vals

            events["F_rec_s"] = events.apply(
                lambda row: calculate_recovery_time(
                    df_interp, row["F_exit_ts"], "Avg_Frequency", *_f_band(row["dKw"]),
                    verify_s=config.recovery_verify_s,
                ) if pd.notnull(row["F_exit_ts"]) else None,
                axis=1,
            )
        else:
            events["F_exit_ts"] = pd.NaT
            events["F_rec_upper"] = np.nan
            events["F_rec_lower"] = np.nan
            events["F_dev"] = np.nan
            events["F_rec_s"] = np.nan

        # Detect events where V or F was already out of band at event time
        # (not recovered from a previous step).
        def _already_out_of_band(ts, column, upper, lower):
            """True if signal was out of band in the pre-event steady state.

            Checks a 1 s window ending 2 s before the event so the reading
            reflects the steady state, not the beginning of the transient
            response to the load change.
            """
            window_end = ts - pd.Timedelta(seconds=2)
            window_start = window_end - pd.Timedelta(seconds=1)
            pre = df_interp[
                (df_interp["Timestamp"] >= window_start) &
                (df_interp["Timestamp"] <= window_end)
            ]
            if pre.empty or column not in pre.columns:
                return False
            val = pd.to_numeric(pre[column].iloc[-1], errors="coerce")
            if pd.isna(val):
                return False
            return val < lower or val > upper

        if "V_exit_ts" in events.columns:
            events["V_not_recovered"] = events["Timestamp"].apply(
                lambda ts: _already_out_of_band(ts, "Avg_Voltage_LL", v_upper, v_lower)
                if "Avg_Voltage_LL" in df_interp.columns else False
            )
        else:
            events["V_not_recovered"] = False

        if "F_exit_ts" in events.columns:
            events["F_not_recovered"] = events.apply(
                lambda row: _already_out_of_band(
                    row["Timestamp"], "Avg_Frequency",
                    row.get("F_rec_upper", nom_f * (1 + tol_f / 100)),
                    row.get("F_rec_lower", nom_f * (1 - tol_f / 100)),
                ) if "Avg_Frequency" in df_interp.columns else False,
                axis=1,
            )
        else:
            events["F_not_recovered"] = False

        # Apply compliance check to each event
        compliance = events.apply(lambda row: check_compliance(row, config), axis=1)
        events = pd.concat([events, compliance], axis=1)

    return df_proc, events
