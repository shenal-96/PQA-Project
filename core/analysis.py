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
    # Asymmetric voltage recovery bands (absolute V).
    # Load increase (dKw > 0): voltage drops → lower band matters more.
    # Load decrease (dKw <= 0): voltage rises → upper band matters more.
    volt_recovery_upper_increase: float = 419.15  # 415 * 1.01
    volt_recovery_lower_increase: float = 410.85  # 415 * 0.99
    volt_recovery_upper_decrease: float = 419.15
    volt_recovery_lower_decrease: float = 410.85
    # Asymmetric max deviation limits (%).
    # Load increase (dKw > 0): signal drops → lower_pct governs.
    # Load decrease (dKw <= 0): signal rises → upper_pct governs.
    volt_max_dev_pct_increase: float = 15.0
    volt_max_dev_pct_decrease: float = 15.0
    freq_max_dev_pct_increase: float = 7.0
    freq_max_dev_pct_decrease: float = 7.0
    # After a sustained in-band window is found, keep verifying for this many
    # seconds.  If the signal exits the band again during verification
    # (oscillation), the candidate is discarded and the search resumes.
    recovery_verify_s: float = 6.0
    # When True, skip 100ms resampling and use raw data directly as df_interp.
    # Use for high-frequency sources (e.g. WinScope ~200ms) that don't need upsampling.
    skip_interpolation: bool = False
    # Recovery time above which the event is flagged as a *potential fault*
    # (separate from compliance fail). Long V/F recovery on a real generator
    # usually indicates broken set-points or hardware issues — worth surfacing
    # distinctly from "exceeded the ISO recovery limit".
    fault_recovery_threshold_s: float = 10.0
    # ── Optional ISO 8528-5 two-band frequency evaluation ────────────────────
    # When False (default) the freq_recovery_* fields above are used for BOTH
    # the stopwatch start (band exit) and stop (recovery re-entry) — current
    # behaviour, byte-identical. When True the stopwatch STARTS when frequency
    # leaves the tighter β_f start band (freq_start_* below) and STOPS when it
    # permanently re-enters the wider α_f stop band (which is carried by the
    # existing freq_recovery_* fields). Also enables the §7 pre-step /
    # post-recovery steady-state checks for both voltage and frequency.
    # Voltage stays single-band (ΔU_st for both start and stop) per the spec.
    iso_8528_5_mode: bool = False
    # β_f start band (absolute Hz). Defaults equal the stop-band defaults so
    # that if these are ever read while iso_8528_5_mode is False the start band
    # equals the stop band and behaviour is unchanged.
    freq_start_upper_increase: float = 50.50
    freq_start_lower_increase: float = 49.75
    freq_start_upper_decrease: float = 50.25
    freq_start_lower_decrease: float = 49.50
    # ── Optional ISO 8528-5 steady-state (δ band) evaluation ─────────────────
    # Independent of the transient/recovery analysis above. When enabled, the
    # record is segmented into the stable "dwell" windows BETWEEN detected
    # load-step events and EVERY voltage/frequency sample in each dwell is
    # checked against the tight δU / δf bands from ISO 8528-5 Table 4 — NOT the
    # α/β recovery bands. Only meaningful for staged load-bank tests (e.g. 25 /
    # 50 / 75 / 100 % held for a dwell period), so it is opt-in per CSV/test.
    steady_state_enabled: bool = False
    steady_voltage_band_pct: float = 2.5   # δU around nominal V (L-L), ±%
    steady_freq_band_pct: float = 2.0      # δf around nominal frequency, ±%
    steady_dwell_min_s: float = 30.0       # ignore plateaus shorter than this
    steady_exclusion_s: float = 10.0       # trim each side of a dwell (settling tail)
    # Rated load (kW) for labelling each dwell as a % of rated (25/50/75/100).
    # None → dwell load % is not computed. Also surfaced to reports elsewhere.
    rated_load_kw: float | None = None

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


def detect_logger_format(columns):
    """Return 'miro', 'hioki', or 'unknown' based on column-name fingerprints.

    A CSV is recognised as Hioki / generic only when it carries a timestamp
    column AND at least one of the expected voltage / frequency columns \u2014
    otherwise we'd silently route any random CSV through the Hioki branch
    and surface confusing downstream errors. Returning 'unknown' lets the
    caller flag the file as unsupported before analysis runs.
    """
    cols = {str(c).replace("\ufeff", "").replace("\x00", "").strip() for c in columns}
    miro_markers = {"RMS-VA-AVG [V]", "FREQ-VA-AVG [Hz]", "kW-PTOTAL-AVG [kW]"}
    if any(m in cols for m in miro_markers):
        return "miro"
    has_time = bool({"Timestamp", "PC Time"} & cols) or ({"Date", "Time"} <= cols)
    has_freq = "Freq_AVG" in cols
    has_voltage = bool({
        "U1_rms_AVG", "U2_rms_AVG", "U3_rms_AVG",
        "U12_rms_AVG", "U23_rms_AVG", "U31_rms_AVG", "U_avg_AVG",
    } & cols)
    # All three required for a green "Hioki / generic" classification —
    # missing any one means the CSV cannot drive a complete compliance run,
    # so flag it as unknown and let the sidebar banner tell the user which
    # column to re-export.
    if has_time and has_freq and has_voltage:
        return "hioki"
    return "unknown"


# Required-column expectations surfaced in error messages so the user knows
# exactly what is missing from their CSV export. Kept here (not in app.py)
# so analysis.py remains the single source of truth for column requirements.
EXPECTED_HIOKI_COLUMNS = {
    "timestamp": ["Timestamp", "PC Time", "Date + Time"],
    "voltage": [
        "U12_rms_AVG, U23_rms_AVG, U31_rms_AVG (L-L)",
        "U1_rms_AVG, U2_rms_AVG, U3_rms_AVG (L-N)",
        "U_avg_AVG (single-phase L-L average)",
    ],
    "frequency": ["Freq_AVG"],
    "power_optional": ["P_sum_AVG"],
    "current_optional": ["I1_rms_AVG, I2_rms_AVG, I3_rms_AVG"],
}


def load_miro_csv(file_path_or_buffer):
    """
    Load a Miro logger CSV and return a DataFrame compatible with perform_analysis.

    Renames Miro column names to pipeline-standard names and converts the
    total kW column from kW \u2192 W so the pipeline's /1000 divisor is consistent.
    Voltages stay in L-N form; AnalysisConfig.ln_to_ll_mode="auto" detects
    U1/U2/U3 as L-N and applies \u00d7\u221a3 downstream.
    """
    df = pd.read_csv(file_path_or_buffer, sep=None, engine="python", encoding="latin-1")
    df.columns = [str(c).replace("\ufeff", "").replace("\x00", "").strip() for c in df.columns]

    rename_map = {
        "RMS-VA-AVG [V]":    "U1_rms_AVG",
        "RMS-VB-AVG [V]":    "U2_rms_AVG",
        "RMS-VC-AVG [V]":    "U3_rms_AVG",
        "RMS-IA-AVG [A]":    "I1_rms_AVG",
        "RMS-IB-AVG [A]":    "I2_rms_AVG",
        "RMS-IC-AVG [A]":    "I3_rms_AVG",
        "FREQ-VA-AVG [Hz]":  "Freq_AVG",
        "TPF-PTOTAL-AVG":    "PF_sum_AVG",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    if "kW-PTOTAL-AVG [kW]" in df.columns:
        df["P_sum_AVG"] = pd.to_numeric(df["kW-PTOTAL-AVG [kW]"], errors="coerce") * 1000

    df["Timestamp"] = robust_to_datetime(df["Timestamp"])
    # Stable sort so that rows sharing the same whole-second timestamp keep
    # their original CSV order — they were written in chronological sample
    # order, and a non-stable sort would scramble them, producing fake
    # load-step oscillations after sub-second redistribution below.
    df = (
        df.dropna(subset=["Timestamp"])
        .sort_values("Timestamp", kind="mergesort")
        .reset_index(drop=True)
    )

    # Miro CSVs only have whole-second timestamp resolution. When the logger
    # records faster than 1 Hz, multiple rows share the same Timestamp value,
    # which breaks anything that assumes monotonically increasing timestamps
    # (sample-interval detection, resampling, sustain/verify counts, plotting).
    # Distribute same-second rows evenly across the second so the data carries
    # an honest sub-second grid: rows i of N at the same second t become
    # t + (i / N) seconds.
    if not df.empty:
        ts = df["Timestamp"]
        grp = df.groupby(ts, sort=False)
        pos = grp.cumcount()
        size = grp["Timestamp"].transform("size")
        offset_s = (pos / size).where(size > 1, 0.0)
        df["Timestamp"] = ts + pd.to_timedelta(offset_s, unit="s")
    return df


def load_and_prepare_csv(file_path_or_buffer, start_time=None, end_time=None):
    """
    Load a CSV file and prepare it for analysis.

    Auto-detects the logger format (Hioki/generic vs Miro) by inspecting the
    header, then dispatches to the appropriate loader. The detected format is
    stashed on df.attrs["logger_format"] for the UI to surface.

    Parameters:
        file_path_or_buffer: path string or file-like object
        start_time: optional HH:MM:SS string to filter start
        end_time: optional HH:MM:SS string to filter end

    Returns:
        DataFrame with a 'Timestamp' column.
    """
    try:
        header_df = pd.read_csv(file_path_or_buffer, nrows=0, sep=None, engine="python")
    except UnicodeDecodeError:
        if hasattr(file_path_or_buffer, "seek"):
            file_path_or_buffer.seek(0)
        header_df = pd.read_csv(file_path_or_buffer, nrows=0, sep=None, engine="python", encoding="latin-1")
    fmt = detect_logger_format(list(header_df.columns))

    if hasattr(file_path_or_buffer, "seek"):
        file_path_or_buffer.seek(0)

    if fmt == "miro":
        df = load_miro_csv(file_path_or_buffer)
    else:
        try:
            df = pd.read_csv(file_path_or_buffer, sep=None, engine="python")
        except UnicodeDecodeError:
            if hasattr(file_path_or_buffer, "seek"):
                file_path_or_buffer.seek(0)
            df = pd.read_csv(file_path_or_buffer, sep=None, engine="python", encoding="latin-1")
        df.columns = [str(c).replace("\ufeff", "").replace("\x00", "").replace(" (Q)", "").strip() for c in df.columns]

        if "PC Time" in df.columns:
            df["Timestamp"] = robust_to_datetime(df["PC Time"])
        elif "Date" in df.columns and "Time" in df.columns:
            df["Timestamp"] = robust_to_datetime(df["Date"] + " " + df["Time"])
        else:
            df["Timestamp"] = robust_to_datetime(df.iloc[:, 1])

        df = df.dropna(subset=["Timestamp"]).sort_values("Timestamp").reset_index(drop=True)

    if start_time and end_time and not df.empty:
        try:
            df_date = df["Timestamp"].dt.date.iloc[0]
            start_dt = pd.to_datetime(f"{df_date} {start_time}")
            end_dt = pd.to_datetime(f"{df_date} {end_time}")
            df = df[(df["Timestamp"] >= start_dt) & (df["Timestamp"] <= end_dt)]
        except Exception as e:
            print(f"Time filtering error: {e}")

    df.attrs["logger_format"] = fmt
    return df


def filter_time_window(df, start=None, end=None):
    """Restrict ``df`` to the inclusive ``[start, end]`` Timestamp window.

    ``start`` / ``end`` are absolute datetimes (ISO strings or anything
    ``pd.to_datetime`` accepts); either may be ``None`` to leave that edge open.
    Returns a filtered copy with ``df.attrs`` (e.g. ``logger_format``) preserved.
    Invalid bounds are ignored rather than raising, so a bad picker value can
    never block analysis.
    """
    if df is None or getattr(df, "empty", True) or "Timestamp" not in getattr(df, "columns", []):
        return df
    if not start and not end:
        return df
    ts = df["Timestamp"]
    mask = pd.Series(True, index=df.index)
    try:
        if start:
            mask &= ts >= pd.to_datetime(start)
        if end:
            mask &= ts <= pd.to_datetime(end)
    except Exception as exc:  # noqa: BLE001 — bad bound -> no filtering
        print(f"Time window filtering error: {exc}")
        return df
    out = df[mask].reset_index(drop=True)
    out.attrs.update(df.attrs)
    return out


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

    # Derive the actual sample interval from the data instead of assuming a
    # 100ms grid. This matters when skip_interpolation=True is used with a
    # source that is NOT 100ms (e.g. a Miro CSV at 1 s, or WinScope at 200 ms).
    if len(timestamps) >= 2:
        diffs_ns = np.diff(timestamps).astype("timedelta64[ns]").astype(np.int64)
        sample_interval_s = max(float(np.median(diffs_ns)) / 1e9, 1e-6)
    else:
        sample_interval_s = 0.1
    sustain_pts = max(1, int(round(sustain_s / sample_interval_s)))
    verify_pts = max(1, int(round(verify_s / sample_interval_s)))

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
        # Select applicable limit based on load direction.
        if row.get("dKw", 0) > 0:  # load increase → voltage drops → use lower limit
            v_max = row.get("V_max_dev_lower_pct", config.voltage_max_deviation_pct)
        else:  # load decrease → voltage rises → use upper limit
            v_max = row.get("V_max_dev_upper_pct", config.voltage_max_deviation_pct)
        if pd.isna(v_max):
            v_max = config.voltage_max_deviation_pct
        if v_dev_pct > v_max:
            status = "Fail"
            reasons.append(f"Voltage Dev {v_dev_pct:.1f}% > {v_max:.1f}%")
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
    # Select applicable limit based on load direction.
    if row.get("dKw", 0) > 0:  # load increase → freq drops → use lower limit
        f_max = row.get("F_max_dev_lower_pct", config.frequency_max_deviation_pct)
    else:  # load decrease → freq rises → use upper limit
        f_max = row.get("F_max_dev_upper_pct", config.frequency_max_deviation_pct)
    if pd.isna(f_max):
        f_max = config.frequency_max_deviation_pct
    if f_dev_pct > f_max:
        status = "Fail"
        reasons.append(f"Freq Dev {f_dev_pct:.1f}% > {f_max:.1f}%")
    # Only check recovery if frequency actually left the tolerance band.
    f_exited = pd.notnull(row.get("F_exit_ts"))
    if f_exited:
        if pd.isna(row["F_rec_s"]):
            status = "Fail"
            reasons.append("Freq did not recover")
        elif row["F_rec_s"] > config.frequency_recovery_time_s:
            status = "Fail"
            reasons.append(f"F Recovery {row['F_rec_s']:.1f}s > {config.frequency_recovery_time_s}s")

    # ── ISO 8528-5 §7 steady-state pass/fail (optional) ──────────────────
    # Pre-step (#1): the signal must already sit within its steady-state band
    # before the load step. Post-step (#4): it must re-establish steady state
    # after recovery — surfaced only when recovery itself passed, so a
    # not-recovered event is not penalised twice. Gated on ISO mode so legacy
    # Failure_Reasons are unchanged; a missing column defaults to "ok".
    # NB: these columns hold numpy.bool_, for which `x is False` is always
    # False — use `not row.get(..., True)` instead.
    if getattr(config, "iso_8528_5_mode", False):
        if not row.get("F_presstep_ok", True):
            status = "Fail"
            reasons.append("Freq not in steady-state band before load step")
        if not row.get("V_presstep_ok", True):
            status = "Fail"
            reasons.append("Voltage not in steady-state band before load step")
        if not row.get("F_poststep_ok", True) and pd.notnull(row.get("F_rec_s")):
            status = "Fail"
            reasons.append("Freq did not hold steady state after recovery")
        if not row.get("V_poststep_ok", True) and pd.notnull(row.get("V_rec_s")):
            status = "Fail"
            reasons.append("Voltage did not hold steady state after recovery")

    # ── Potential-fault flag ─────────────────────────────────────────────
    # Recovery times that grossly exceed the ISO limit are usually a sign of
    # broken set-points or hardware issues, not just marginal performance.
    # Surface them separately from compliance fail so the operator can
    # investigate the equipment rather than just retuning the spec.
    fault = False
    fault_reasons = []
    fault_thr = float(getattr(config, "fault_recovery_threshold_s", 10.0))
    v_rec = row.get("V_rec_s")
    if pd.notnull(row.get("V_exit_ts")):
        if pd.isna(v_rec):
            fault = True
            fault_reasons.append("Voltage did not recover")
        elif float(v_rec) > fault_thr:
            fault = True
            fault_reasons.append(f"V Recovery {float(v_rec):.1f}s > {fault_thr:.0f}s")
    f_rec = row.get("F_rec_s")
    if pd.notnull(row.get("F_exit_ts")):
        if pd.isna(f_rec):
            fault = True
            fault_reasons.append("Frequency did not recover")
        elif float(f_rec) > fault_thr:
            fault = True
            fault_reasons.append(f"F Recovery {float(f_rec):.1f}s > {fault_thr:.0f}s")

    return pd.Series(
        [status, "; ".join(reasons), bool(fault), "; ".join(fault_reasons)],
        index=["Compliance_Status", "Failure_Reasons", "Potential_Fault", "Fault_Reasons"],
    )


# ── ISO 8528-5 steady-state (δ band) analysis ───────────────────────────────
# Evaluates whether the generator holds voltage/frequency inside the tight δ
# tolerance bands during STABLE loaded operation (the dwell periods between load
# steps). Distinct from transient analysis: it uses the δ bands, never the α/β
# recovery bands, and it inspects raw measured samples (df_proc), never the
# interpolated df_interp.

# Hunting / oscillation thresholds (qualitative red flag — does NOT fail a dwell
# on its own; even in-band sustained cyclic oscillation is worth surfacing).
_HUNT_MIN_CYCLES = 3.0       # at least this many oscillation cycles within the dwell
_HUNT_PTP_BAND_FRAC = 0.4    # peak-to-peak must reach this fraction of the band width
_HUNT_DEADBAND_FRAC = 0.05   # ignore mean-crossings smaller than this fraction of band


def detect_steady_windows(df_proc, df_events, config: AnalysisConfig):
    """Auto-segment the record into stable dwell windows between transient events.

    A dwell window is the span between the end of one load-step event and the
    start of the next (plus the spans before the first event and after the last).
    Each window is trimmed by ``steady_exclusion_s`` on both sides to drop the
    AVR/governor settling tail adjacent to a load step, then discarded if shorter
    than ``steady_dwell_min_s``. When there are no detected events the whole
    record is one candidate window. Returns a list of ``{"start", "end"}`` dicts
    (pandas Timestamps).
    """
    if df_proc is None or df_proc.empty or "Timestamp" not in df_proc.columns:
        return []
    ts = pd.to_datetime(df_proc["Timestamp"])
    rec_start, rec_end = ts.iloc[0], ts.iloc[-1]

    boundaries = []  # (lo, hi) pairs bracketing each candidate dwell
    if df_events is None or df_events.empty or "Start_Timestamp" not in df_events.columns:
        boundaries.append((rec_start, rec_end))
    else:
        ev = df_events.sort_values("Start_Timestamp")
        starts = pd.to_datetime(ev["Start_Timestamp"]).tolist()
        ends = pd.to_datetime(
            ev["End_Timestamp"] if "End_Timestamp" in ev.columns else ev["Start_Timestamp"]
        ).tolist()
        boundaries.append((rec_start, starts[0]))                 # before first step
        for i in range(len(starts) - 1):
            boundaries.append((ends[i], starts[i + 1]))           # between steps
        boundaries.append((ends[-1], rec_end))                    # after last step

    excl = pd.Timedelta(seconds=float(config.steady_exclusion_s))
    min_dur = float(config.steady_dwell_min_s)
    windows = []
    for lo, hi in boundaries:
        a, b = lo + excl, hi - excl
        if (b - a).total_seconds() >= min_dur:
            windows.append({"start": a, "end": b})
    return windows


def _band_stats(vals, prefix, lower, upper, nom):
    """Per-metric stats for one dwell: min/max/mean, out-of-band count and the
    worst absolute deviation from nominal (%). ``vals`` is a cleaned numeric
    Series."""
    if vals.empty:
        return {f"{prefix}_min": None, f"{prefix}_max": None, f"{prefix}_mean": None,
                f"{prefix}_n_out": 0, f"{prefix}_pct_out": None, f"{prefix}_worst_dev_pct": None}
    out_mask = (vals < lower) | (vals > upper)
    n_out = int(out_mask.sum())
    worst = float((vals - nom).abs().max()) / nom * 100.0
    dec = 2 if nom > 100 else 3
    return {
        f"{prefix}_min": round(float(vals.min()), dec),
        f"{prefix}_max": round(float(vals.max()), dec),
        f"{prefix}_mean": round(float(vals.mean()), dec),
        f"{prefix}_n_out": n_out,
        f"{prefix}_pct_out": round(n_out / len(vals) * 100.0, 2),
        f"{prefix}_worst_dev_pct": round(worst, 2),
    }


def _detect_hunting(vals, lower, upper):
    """Detect sustained cyclic oscillation (governor/AVR hunting) even when every
    sample stays in band. Counts mean-crossings (with a small deadband to ignore
    measurement noise) and checks peak-to-peak amplitude against the band width.
    Returns ``{"cycles", "ptp"}`` when hunting is detected, else None."""
    if len(vals) < 6:
        return None
    arr = vals.to_numpy(dtype=float)
    band_w = upper - lower
    if band_w <= 0:
        return None
    ptp = float(arr.max() - arr.min())
    if ptp < _HUNT_PTP_BAND_FRAC * band_w:
        return None
    centered = arr - arr.mean()
    dead = _HUNT_DEADBAND_FRAC * band_w
    signs = np.where(centered > dead, 1, np.where(centered < -dead, -1, 0))
    signs = signs[signs != 0]
    if signs.size < 2:
        return None
    flips = int(np.sum(signs[1:] != signs[:-1]))
    cycles = flips / 2.0
    if cycles < _HUNT_MIN_CYCLES:
        return None
    return {"cycles": cycles, "ptp": ptp}


def evaluate_steady_window(df_proc, start_ts, end_ts, config: AnalysisConfig,
                           index=0, label=None):
    """Evaluate one dwell window against the δ bands. Returns a flat dict (one
    steady-state result row). Pass/Fail is driven purely by samples leaving the
    δ band; hunting is reported separately as a qualitative flag."""
    start_ts, end_ts = pd.Timestamp(start_ts), pd.Timestamp(end_ts)
    nom_v, nom_f = config.nominal_voltage, config.nominal_frequency
    v_half = nom_v * config.steady_voltage_band_pct / 100.0
    f_half = nom_f * config.steady_freq_band_pct / 100.0
    v_lower, v_upper = nom_v - v_half, nom_v + v_half
    f_lower, f_upper = nom_f - f_half, nom_f + f_half

    tcol = pd.to_datetime(df_proc["Timestamp"])
    seg = df_proc[(tcol >= start_ts) & (tcol <= end_ts)]
    duration = (end_ts - start_ts).total_seconds()

    rec = {
        "Window_Index": int(index),
        "Start_Timestamp": start_ts,
        "End_Timestamp": end_ts,
        "Duration_s": round(duration, 1),
        "n_samples": int(len(seg)),
        "V_band_lower": round(v_lower, 2), "V_band_upper": round(v_upper, 2),
        "F_band_lower": round(f_lower, 3), "F_band_upper": round(f_upper, 3),
    }

    # Load level (mean kW over the dwell) and % of rated when a rating is known.
    kw = pd.to_numeric(seg["Avg_kW"], errors="coerce").dropna() if "Avg_kW" in seg.columns else pd.Series(dtype=float)
    mean_kw = float(kw.mean()) if not kw.empty else None
    rec["Mean_kW"] = round(mean_kw, 1) if mean_kw is not None else None
    rated = getattr(config, "rated_load_kw", None)
    auto_label = None
    if mean_kw is not None and rated:
        load_pct = mean_kw / float(rated) * 100.0
        rec["Load_Pct"] = round(load_pct, 1)
        nearest = min((25, 50, 75, 100), key=lambda x: abs(x - load_pct))
        auto_label = f"{nearest}%" if abs(nearest - load_pct) <= 7 else f"{load_pct:.0f}%"
    else:
        rec["Load_Pct"] = None
    # Explicit user label wins; otherwise the auto % label (may be None).
    rec["Load_Label"] = label if label is not None else auto_label

    v = pd.to_numeric(seg["Avg_Voltage_LL"], errors="coerce").dropna() if "Avg_Voltage_LL" in seg.columns else pd.Series(dtype=float)
    f = pd.to_numeric(seg["Avg_Frequency"], errors="coerce").dropna() if "Avg_Frequency" in seg.columns else pd.Series(dtype=float)
    rec.update(_band_stats(v, "V", v_lower, v_upper, nom_v))
    rec.update(_band_stats(f, "F", f_lower, f_upper, nom_f))

    reasons, status = [], "Pass"
    if rec["V_n_out"] > 0:
        status = "Fail"
        reasons.append(f"Voltage out of δU band on {rec['V_n_out']} sample(s) (worst {rec['V_worst_dev_pct']:.2f}%)")
    if rec["F_n_out"] > 0:
        status = "Fail"
        reasons.append(f"Frequency out of δf band on {rec['F_n_out']} sample(s) (worst {rec['F_worst_dev_pct']:.2f}%)")

    v_hunt = _detect_hunting(v, v_lower, v_upper)
    f_hunt = _detect_hunting(f, f_lower, f_upper)
    hunt_reasons = []
    if v_hunt:
        hunt_reasons.append(f"Voltage oscillation ~{v_hunt['cycles']:.0f} cycles, p-p {v_hunt['ptp']:.1f} V")
    if f_hunt:
        hunt_reasons.append(f"Frequency oscillation ~{f_hunt['cycles']:.0f} cycles, p-p {f_hunt['ptp']:.2f} Hz")
    rec["Hunting"] = bool(v_hunt or f_hunt)
    rec["Hunting_Reasons"] = "; ".join(hunt_reasons)

    rec["Status"] = status
    rec["Failure_Reasons"] = "; ".join(reasons)
    return rec


def analyze_steady_state(df_proc, df_events, config: AnalysisConfig, windows=None):
    """Evaluate generator steady-state stability against the ISO 8528-5 δ bands.

    Separate from the transient/recovery analysis: it inspects the stable dwell
    periods (every sample, on raw ``df_proc`` — never ``df_interp``) against the
    tight δU / δf bands, NOT the α/β recovery bands. ``windows`` lets the caller
    pass user-confirmed/edited dwell ranges (the hybrid confirm flow) as a list
    of ``{"start", "end", "label"?, "index"?}`` dicts; when None they are
    auto-detected via :func:`detect_steady_windows`. Returns a DataFrame with one
    row per dwell window (empty DataFrame when none qualify).
    """
    if windows is None:
        windows = detect_steady_windows(df_proc, df_events, config)
    rows = [
        evaluate_steady_window(
            df_proc, w["start"], w["end"], config,
            index=w.get("index", i), label=w.get("label"),
        )
        for i, w in enumerate(windows)
    ]
    return pd.DataFrame(rows)


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
                # Anchor the merge window at Start_Timestamp and absorb every
                # raw sample that lands inside it, regardless of sign. Large
                # block-load ramps (e.g. 0 → 2000 kW over 4 s) are not
                # monotonic at high sample rates — the kW reading oscillates
                # as the generator catches up, producing alternating ±dKw raw
                # rows. Merging only same-direction rows would split the ramp
                # into many sub-events; the algebraic sum is what represents
                # the true net step.
                within_window = (row["Timestamp"] - curr["Start_Timestamp"]).total_seconds() <= config.detection_window_s
                if within_window:
                    curr["Total_dKw"] += row["dKw"]
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
        # Drop groups whose merged net change ended up below threshold —
        # these are oscillations around a stable load that produced
        # individual above-threshold raw rows but no real net step.
        events = events[events["Total_dKw"].abs() > float(thresh_kw)].reset_index(drop=True)

    if not events.empty:
        events["dKw_abs"] = events["Total_dKw"].abs()
        events["dKw"] = events["Total_dKw"]
        events["Timestamp"] = events["Start_Timestamp"]

    # --- Recovery times & compliance (all from interpolated data) ---
    if not events.empty:
        tol_v = config.voltage_tolerance_pct
        tol_f = config.frequency_tolerance_pct

        # Voltage band is direction-dependent (asymmetric).
        # Load increase (dKw > 0): voltage drops → use increase band.
        # Load decrease (dKw <= 0): voltage rises → use decrease band.
        def _v_band(dkw):
            if dkw > 0:
                return (config.volt_recovery_upper_increase,
                        config.volt_recovery_lower_increase)
            return (config.volt_recovery_upper_decrease,
                    config.volt_recovery_lower_decrease)

        if "Avg_Voltage_LL" in df_interp.columns and df_interp["Avg_Voltage_LL"].notna().any():
            events["V_rec_upper"] = events["dKw"].apply(
                lambda dk: config.volt_recovery_upper_increase if dk > 0
                           else config.volt_recovery_upper_decrease
            )
            events["V_rec_lower"] = events["dKw"].apply(
                lambda dk: config.volt_recovery_lower_increase if dk > 0
                           else config.volt_recovery_lower_decrease
            )
            # Compute V_dev first so we can gate the forward scan on it.
            events["V_dev"] = events.apply(
                lambda row: _measured_extreme(df_proc, row["Timestamp"], "Avg_Voltage_LL",
                                              row["dKw"], window_s=config.snapshot_window_s / 2.0),
                axis=1,
            )
            v_exit_vals = []
            for _, row in events.iterrows():
                ts = row["Timestamp"]
                v_upper, v_lower = _v_band(row["dKw"])
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
                    df_interp, row["V_exit_ts"], "Avg_Voltage_LL", *_v_band(row["dKw"]),
                    verify_s=config.recovery_verify_s,
                ) if pd.notnull(row["V_exit_ts"]) else None,
                axis=1,
            )
        else:
            events["V_exit_ts"] = pd.NaT
            events["V_rec_upper"] = np.nan
            events["V_rec_lower"] = np.nan
            events["V_dev"] = np.nan
            events["V_rec_s"] = np.nan

        if "Avg_Frequency" in df_interp.columns and df_interp["Avg_Frequency"].notna().any():
            # Frequency band is asymmetric and direction-dependent.
            # Load increase (dKw > 0): freq drops → use increase band.
            # Load decrease (dKw <= 0): freq rises → use decrease band.
            # The recovery band is the STOP band (α_f in ISO 8528-5 terms):
            # the stopwatch stops when frequency permanently re-enters it.
            def _f_band(dkw):
                if dkw > 0:
                    return (config.freq_recovery_upper_increase,
                            config.freq_recovery_lower_increase)
                return (config.freq_recovery_upper_decrease,
                        config.freq_recovery_lower_decrease)

            # The exit band is the START band. In legacy (single-band) mode it
            # is identical to the recovery band, so behaviour is unchanged. In
            # ISO 8528-5 two-band mode it is the tighter β_f band: the stopwatch
            # starts the moment frequency leaves β_f, while recovery is still
            # measured against the wider α_f band above.
            def _f_start_band(dkw):
                if not config.iso_8528_5_mode:
                    return _f_band(dkw)
                if dkw > 0:
                    return (config.freq_start_upper_increase,
                            config.freq_start_lower_increase)
                return (config.freq_start_upper_decrease,
                        config.freq_start_lower_decrease)

            events["F_rec_upper"] = events["dKw"].apply(
                lambda dk: config.freq_recovery_upper_increase if dk > 0
                           else config.freq_recovery_upper_decrease
            )
            events["F_rec_lower"] = events["dKw"].apply(
                lambda dk: config.freq_recovery_lower_increase if dk > 0
                           else config.freq_recovery_lower_decrease
            )
            # In ISO mode also expose the β_f start band per event so the
            # snapshot can draw it and place the exit marker on the right line.
            if config.iso_8528_5_mode:
                events["F_start_upper"] = events["dKw"].apply(
                    lambda dk: config.freq_start_upper_increase if dk > 0
                               else config.freq_start_upper_decrease
                )
                events["F_start_lower"] = events["dKw"].apply(
                    lambda dk: config.freq_start_lower_increase if dk > 0
                               else config.freq_start_lower_decrease
                )
            # Compute F_dev first so we can gate the forward scan on it.
            events["F_dev"] = events.apply(
                lambda row: _measured_extreme(df_proc, row["Timestamp"], "Avg_Frequency",
                                              row["dKw"], window_s=config.snapshot_window_s / 2.0),
                axis=1,
            )
            f_exit_vals = []
            for _, row in events.iterrows():
                ts = row["Timestamp"]
                # Exit (stopwatch start) uses the START band — β_f in ISO mode,
                # identical to the recovery band otherwise.
                f_upper, f_lower = _f_start_band(row["dKw"])
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

        # Per-event deviation limit columns.
        # Upper line = limit for signal rise (load decrease direction).
        # Lower line = limit for signal drop (load increase direction).
        events["V_max_dev_upper_pct"] = config.volt_max_dev_pct_decrease
        events["V_max_dev_lower_pct"] = config.volt_max_dev_pct_increase
        events["F_max_dev_upper_pct"] = config.freq_max_dev_pct_decrease
        events["F_max_dev_lower_pct"] = config.freq_max_dev_pct_increase

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
            events["V_not_recovered"] = events.apply(
                lambda row: _already_out_of_band(
                    row["Timestamp"], "Avg_Voltage_LL",
                    row.get("V_rec_upper", nom_v * (1 + tol_v / 100)),
                    row.get("V_rec_lower", nom_v * (1 - tol_v / 100)),
                ) if "Avg_Voltage_LL" in df_interp.columns else False,
                axis=1,
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

        # ── ISO 8528-5 §7 steady-state checks (optional) ─────────────────────
        # Only evaluated in ISO mode so legacy output is byte-identical.
        if config.iso_8528_5_mode:
            def _steady_after_recovery(exit_ts, rec_s, column, upper, lower):
                """True unless the signal drifted back out of the steady-state
                band AFTER the recovery verify window (§7 #4). Returns True when
                there was no recovery to check, the metric is missing, or the
                post-recovery window runs past the data — never fabricate a
                failure. The recovery algorithm already guarantees sustained
                in-band data for recovery_verify_s after re-entry, so this only
                inspects the first reading beyond that window."""
                if pd.isna(exit_ts) or pd.isna(rec_s):
                    return True
                t_stop = pd.Timestamp(exit_ts) + pd.Timedelta(seconds=float(rec_s))
                w_start = t_stop + pd.Timedelta(seconds=config.recovery_verify_s)
                w_end = w_start + pd.Timedelta(seconds=1)
                post = df_interp[
                    (df_interp["Timestamp"] >= w_start) &
                    (df_interp["Timestamp"] <= w_end)
                ]
                if post.empty or column not in post.columns:
                    return True
                val = pd.to_numeric(post[column].iloc[-1], errors="coerce")
                if pd.isna(val):
                    return True
                return bool(lower <= val <= upper)

            # Pre-step (§7 #1): steady state must be in band before the load step.
            # Frequency uses the α_f stop band, which equals the F_rec_* band the
            # not-recovered test already evaluated — so reuse it directly. Voltage
            # uses the ΔU_st steady-state tolerance band (nom ± tol), NOT the
            # V_rec_* recovery band, per the spec.
            events["F_presstep_ok"] = ~events["F_not_recovered"].astype(bool)
            if "Avg_Voltage_LL" in df_interp.columns:
                events["V_presstep_ok"] = ~events.apply(
                    lambda row: _already_out_of_band(
                        row["Timestamp"], "Avg_Voltage_LL",
                        nom_v * (1 + tol_v / 100), nom_v * (1 - tol_v / 100),
                    ),
                    axis=1,
                )
            else:
                events["V_presstep_ok"] = True

            # Post-step (§7 #4): steady state must re-establish after recovery.
            events["F_poststep_ok"] = events.apply(
                lambda row: _steady_after_recovery(
                    row.get("F_exit_ts"), row.get("F_rec_s"), "Avg_Frequency",
                    row.get("F_rec_upper"), row.get("F_rec_lower"),
                ),
                axis=1,
            )
            events["V_poststep_ok"] = events.apply(
                lambda row: _steady_after_recovery(
                    row.get("V_exit_ts"), row.get("V_rec_s"), "Avg_Voltage_LL",
                    nom_v * (1 + tol_v / 100), nom_v * (1 - tol_v / 100),
                ),
                axis=1,
            )

        # Widen V_dev / F_dev for not-recovered events so the deep dip from the
        # prior step (which is bleeding into this event's window) is captured.
        # Lower bound: prior event's Timestamp, or event_ts - snapshot_window_s/2
        # if there is no prior event. Upper bound: event_ts + snapshot_window_s/2.
        _half_win = config.snapshot_window_s / 2.0
        events = events.reset_index(drop=True)
        for _i in range(len(events)):
            _row = events.iloc[_i]
            _ts = _row["Timestamp"]
            _dkw = _row.get("dKw", 0)
            _prev_ts = events.iloc[_i - 1]["Timestamp"] if _i > 0 else _ts - pd.Timedelta(seconds=_half_win)
            _start = max(_prev_ts, _ts - pd.Timedelta(seconds=_half_win))
            _end = _ts + pd.Timedelta(seconds=_half_win)
            if _row.get("V_not_recovered", False) and "Avg_Voltage_LL" in df_proc.columns:
                _vw = df_proc[(df_proc["Timestamp"] >= _start) & (df_proc["Timestamp"] <= _end)]
                _vv = pd.to_numeric(_vw["Avg_Voltage_LL"], errors="coerce").dropna()
                if not _vv.empty:
                    events.at[_i, "V_dev"] = _vv.min() if _dkw > 0 else _vv.max()
                # Inherit prior event's exit/recovery so the snapshot can render
                # the intersection points for the carry-over dip.
                if _i > 0 and pd.isnull(_row.get("V_exit_ts")):
                    _prev = events.iloc[_i - 1]
                    if pd.notnull(_prev.get("V_exit_ts")):
                        events.at[_i, "V_exit_ts"] = _prev["V_exit_ts"]
                        events.at[_i, "V_rec_s"] = _prev.get("V_rec_s")
            if _row.get("F_not_recovered", False) and "Avg_Frequency" in df_proc.columns:
                _fw = df_proc[(df_proc["Timestamp"] >= _start) & (df_proc["Timestamp"] <= _end)]
                _ff = pd.to_numeric(_fw["Avg_Frequency"], errors="coerce").dropna()
                if not _ff.empty:
                    events.at[_i, "F_dev"] = _ff.min() if _dkw > 0 else _ff.max()
                if _i > 0 and pd.isnull(_row.get("F_exit_ts")):
                    _prev = events.iloc[_i - 1]
                    if pd.notnull(_prev.get("F_exit_ts")):
                        events.at[_i, "F_exit_ts"] = _prev["F_exit_ts"]
                        events.at[_i, "F_rec_s"] = _prev.get("F_rec_s")

        # Apply compliance check to each event
        compliance = events.apply(lambda row: check_compliance(row, config), axis=1)
        events = pd.concat([events, compliance], axis=1)

    return df_proc, events
