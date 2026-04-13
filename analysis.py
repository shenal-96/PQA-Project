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


def calculate_recovery_time(df_interp, start_timestamp, metric_column,
                            upper, lower, sustain_s=0.3):
    """
    Calculate recovery time using 100ms-interpolated data with exact crossing detection.

    Measures from start_timestamp (typically the band-exit crossing) to the
    moment the signal re-enters [lower, upper] and stays there for sustain_s.

    Algorithm:
    1. Scan the 100ms grid for the first grid point that begins a sustained
       in-band window (sustain_s seconds of consecutive in-band points).
    2. Once found, linearly interpolate between that point and the preceding
       out-of-band point to find the exact crossing time.

    Parameters:
        upper / lower: absolute band boundaries in signal units (V or Hz).

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

    for i in range(len(within)):
        if not within[i]:
            continue
        end = min(i + sustain_pts, len(within))
        if not np.all(within[i:end]):
            continue

        # Sustained in-band window starts at grid point i.
        # Interpolate back to find the exact band-crossing time between
        # grid point i-1 (out-of-band) and grid point i (in-band).
        if i == 0:
            return (pd.Timestamp(timestamps[0]) - start_timestamp).total_seconds()

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
        return (t_cross - start_timestamp).total_seconds()

    return None


def calculate_exit_time(df_interp, event_timestamp, metric_column,
                        upper, lower, lookback_s=30):
    """
    Find the exact time the signal exited the tolerance band prior to (or at)
    event_timestamp, using linear interpolation for sub-100ms precision.

    Scans backwards through the 100ms interpolated data starting from
    event_timestamp. The first in-band point found (moving backwards) marks
    the transition: that point is in-band, the next point (forward in time)
    is out-of-band. We interpolate between them to find the exact crossing.

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


def _peak_deviation(df, event_ts, column, nominal, window_s=30):
    """
    Return the signed peak deviation (largest absolute excursion from nominal)
    in the `window_s` seconds after event_ts.  Pass df_proc for measured-only
    values, or df_interp for sub-second interpolated values.
    """
    end_ts = event_ts + pd.Timedelta(seconds=window_s)
    subset = df[
        (df["Timestamp"] > event_ts) &
        (df["Timestamp"] <= end_ts)
    ]
    if subset.empty or column not in subset.columns:
        return np.nan
    vals = pd.to_numeric(subset[column], errors="coerce").dropna()
    if vals.empty:
        return np.nan
    deviations = vals - nominal
    peak_idx = deviations.abs().idxmax()
    return deviations[peak_idx]


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

    # Frequency checks
    f_dev_pct = (abs(row["F_dev"]) / nom_f) * 100
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
    pf_cols = [c for c in df.columns if "PF" in c.upper() and "AVG" in c.upper()]
    df_proc["Avg_PF"] = df[pf_cols].apply(pd.to_numeric, errors="coerce").mean(axis=1) if pf_cols else np.nan

    # --- Power & Frequency ---
    df_proc["Avg_kW"] = pd.to_numeric(df.get("P_sum_AVG", 0), errors="coerce") / 1000
    df_proc["Avg_Frequency"] = pd.to_numeric(df.get("Freq_AVG", np.nan), errors="coerce")
    df_proc["dKw"] = df_proc["Avg_kW"].diff().fillna(0)

    # --- Interpolation (100ms) — used only for compliance calculations ---
    # Linear interpolation between 1-second measured points gives sub-second
    # precision for peak deviation and recovery time. This data is NOT used
    # for plotting or snapshots.
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
            events["V_exit_ts"] = events["Timestamp"].apply(
                lambda x: calculate_exit_time(df_interp, x, "Avg_Voltage_LL", v_upper, v_lower)
            )
            events["V_dev"] = events["Timestamp"].apply(
                lambda x: _peak_deviation(df_proc, x, "Avg_Voltage_LL", nom_v)
            )
            events["V_rec_s"] = events.apply(
                lambda row: calculate_recovery_time(
                    df_interp, row["V_exit_ts"], "Avg_Voltage_LL", v_upper, v_lower,
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
            events["F_exit_ts"] = events.apply(
                lambda row: calculate_exit_time(
                    df_interp, row["Timestamp"], "Avg_Frequency",
                    *_f_band(row["dKw"])
                ),
                axis=1,
            )
            events["F_dev"] = events["Timestamp"].apply(
                lambda x: _peak_deviation(df_proc, x, "Avg_Frequency", nom_f)
            )
            events["F_rec_s"] = events.apply(
                lambda row: calculate_recovery_time(
                    df_interp, row["F_exit_ts"], "Avg_Frequency", *_f_band(row["dKw"]),
                ) if pd.notnull(row["F_exit_ts"]) else None,
                axis=1,
            )
        else:
            events["F_exit_ts"] = pd.NaT
            events["F_rec_upper"] = np.nan
            events["F_rec_lower"] = np.nan
            events["F_dev"] = np.nan
            events["F_rec_s"] = np.nan

        # Apply compliance check to each event
        compliance = events.apply(lambda row: check_compliance(row, config), axis=1)
        events = pd.concat([events, compliance], axis=1)

    return df_proc, events
