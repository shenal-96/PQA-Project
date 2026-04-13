"""
Power Quality Analysis - Streamlit Application

Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import os
import shutil
import zipfile
import io
import glob
import datetime
import logging
import json

from analysis import AnalysisConfig, load_and_prepare_csv, perform_analysis, check_compliance, calculate_recovery_time
from visualizations import (
    generate_plots,
    generate_all_snapshots,
    save_compliance_table_as_image,
)
from report import get_placeholder_map, inject_images_to_word, generate_docx, convert_to_pdf
from html_report import get_default_template, generate_html_report

# --- Logging setup ---
LOG_FILE = "/tmp/pqa_debug.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a"),
        logging.StreamHandler(),          # also prints to terminal
    ],
)
log = logging.getLogger("PQA")

# --- Page Config ---
st.set_page_config(
    page_title="PQA - Power Quality Analysis",
    page_icon="\u26a1",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Pin all paths to the script's directory so the app works regardless of
# which directory Streamlit is launched from (important for remote access).
_APP_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Output directories ---
OUTPUT_BASE = os.path.join(_APP_DIR, "output")
GRAPH_DIR = os.path.join(OUTPUT_BASE, "Graphs")
SNAPSHOT_DIR = os.path.join(OUTPUT_BASE, "Snapshots")
IMAGE_DIR = os.path.join(OUTPUT_BASE, "Images")
TEMPLATE_DIR = os.path.join(OUTPUT_BASE, "Template")

# --- Persistent upload directories ---
UPLOADS_CSV_DIR = os.path.join(_APP_DIR, "uploads", "csv")
UPLOADS_TEMPLATE_DIR = os.path.join(_APP_DIR, "uploads", "templates")
os.makedirs(UPLOADS_CSV_DIR, exist_ok=True)
os.makedirs(UPLOADS_TEMPLATE_DIR, exist_ok=True)

# ── Dev-mode settings persistence ────────────────────────────────────────────
DEV_SETTINGS_FILE = "uploads/dev_settings.json"

_DEV_DEFAULTS: dict = {
    "dev_mode": False,
    # CSV selection
    "selected_csv_name": "",
    # Acceptance Criteria
    "apply_iso": False,
    "show_limits": False,
    "show_limits_snapshots": False,
    "show_debug": False,
    "detection_window": 5.0,
    "snapshot_window": 10.0,
    "load_thresh": 50.0,
    "v_tol": 1.0,
    "v_rec": 4.0,
    "v_max_dev": 15.0,
    "f_tol": 0.5,
    "f_rec": 3.0,
    "f_max_dev": 7.0,
    "fri_upper": 50.50,
    "fri_lower": 49.75,
    "frd_upper": 50.25,
    "frd_lower": 49.50,
    # Rated load
    "rated_load_input": "",
    # Display Options
    "nom_v_preset": "415 V  (LV — AU/UK)",
    "nom_v_custom": 415.0,
    "nom_f": 50.0,
    "csv_voltage_type": "Auto-detect (by column names)",
    # Time filter (keyed by CSV path so restore only for the same file)
    "_tf_csv_path": "",
    "tf_start_text": "",
    "tf_end_text": "",
    # Report Details
    "gen_sn": "",
    "site_address": "",
    "custom_text": "",
    "report_format": "Word Template",
}


def _load_dev_settings() -> dict:
    """Return merged settings dict: file values layered on top of defaults."""
    merged = dict(_DEV_DEFAULTS)
    if os.path.exists(DEV_SETTINGS_FILE):
        try:
            with open(DEV_SETTINGS_FILE) as _f:
                merged.update(json.load(_f))
        except Exception:
            pass
    return merged


def _save_dev_settings(ds: dict) -> None:
    try:
        with open(DEV_SETTINGS_FILE, "w") as _f:
            json.dump(ds, _f, indent=2)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────


def init_output_dirs():
    for d in [GRAPH_DIR, SNAPSHOT_DIR, IMAGE_DIR, TEMPLATE_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)


def _recompute_df_interp(df_proc):
    """Rebuild the 100 ms interpolated frame from df_proc (same logic as perform_analysis)."""
    import numpy as np
    num_cols = df_proc.select_dtypes(include=[np.number]).columns
    return (
        df_proc.set_index("Timestamp")[num_cols]
        .resample("100ms")
        .mean()
        .interpolate(method="linear")
        .reset_index()
    )


def _render_event_intersection_controls(idx, row, overrides):
    """
    Render the Voltage + Frequency intersection controls for a single event.
    Called from inside an already-open expander (no wrapper created here).
    `overrides` is st.session_state["intersection_overrides"].
    """
    if idx not in overrides:
        overrides[idx] = {
            "v_exit_offset": 0.0,
            "v_rec_override": None,
            "f_exit_offset": 0.0,
            "f_rec_override": None,
        }
    ov = overrides[idx]

    v_exit_ts  = row.get("V_exit_ts")
    v_rec_auto = row.get("V_rec_s")
    f_exit_ts  = row.get("F_exit_ts")
    f_rec_auto = row.get("F_rec_s")

    vcol, fcol = st.columns(2)

    # ── Voltage ──────────────────────────────────────────────────────────
    with vcol:
        st.markdown("**Voltage**")
        v_exit_valid = pd.notnull(v_exit_ts)

        if v_exit_valid:
            st.caption(f"Auto exit: `{pd.Timestamp(v_exit_ts).strftime('%H:%M:%S.%f')[:-3]}`")
            st.caption(
                f"Auto recovery: `{v_rec_auto:.3f}s`"
                if pd.notnull(v_rec_auto) else "Auto recovery: *not detected*"
            )
            ov["v_exit_offset"] = st.number_input(
                "Exit offset (s)",
                value=float(ov["v_exit_offset"]),
                min_value=-30.0, max_value=30.0, step=0.1, format="%.1f",
                key=f"v_exit_offset_{idx}",
                help="Shift exit crossing earlier (−) or later (+) from auto-detected time",
            )
            if ov["v_exit_offset"] != 0.0:
                adj = pd.Timestamp(v_exit_ts) + pd.Timedelta(seconds=ov["v_exit_offset"])
                st.caption(f"→ Adjusted exit: `{adj.strftime('%H:%M:%S.%f')[:-3]}`")
        else:
            st.caption("*No exit detected — exit offset unavailable*")

        v_override_on = st.checkbox(
            "Override recovery time",
            value=ov["v_rec_override"] is not None,
            key=f"v_rec_on_{idx}",
        )
        if v_override_on:
            default_v = (
                float(ov["v_rec_override"]) if ov["v_rec_override"] is not None
                else (float(v_rec_auto) if pd.notnull(v_rec_auto) else 0.0)
            )
            ov["v_rec_override"] = st.number_input(
                "V Recovery (s)",
                value=default_v,
                min_value=0.0, max_value=120.0, step=0.1, format="%.2f",
                key=f"v_rec_val_{idx}",
            )
        else:
            ov["v_rec_override"] = None

    # ── Frequency ────────────────────────────────────────────────────────
    with fcol:
        st.markdown("**Frequency**")
        f_exit_valid = pd.notnull(f_exit_ts)

        if f_exit_valid:
            st.caption(f"Auto exit: `{pd.Timestamp(f_exit_ts).strftime('%H:%M:%S.%f')[:-3]}`")
            st.caption(
                f"Auto recovery: `{f_rec_auto:.3f}s`"
                if pd.notnull(f_rec_auto) else "Auto recovery: *not detected*"
            )
            ov["f_exit_offset"] = st.number_input(
                "Exit offset (s)",
                value=float(ov["f_exit_offset"]),
                min_value=-30.0, max_value=30.0, step=0.1, format="%.1f",
                key=f"f_exit_offset_{idx}",
                help="Shift exit crossing earlier (−) or later (+) from auto-detected time",
            )
            if ov["f_exit_offset"] != 0.0:
                adj = pd.Timestamp(f_exit_ts) + pd.Timedelta(seconds=ov["f_exit_offset"])
                st.caption(f"→ Adjusted exit: `{adj.strftime('%H:%M:%S.%f')[:-3]}`")
        else:
            st.caption("*No exit detected — exit offset unavailable*")

        f_override_on = st.checkbox(
            "Override recovery time",
            value=ov["f_rec_override"] is not None,
            key=f"f_rec_on_{idx}",
        )
        if f_override_on:
            default_f = (
                float(ov["f_rec_override"]) if ov["f_rec_override"] is not None
                else (float(f_rec_auto) if pd.notnull(f_rec_auto) else 0.0)
            )
            ov["f_rec_override"] = st.number_input(
                "F Recovery (s)",
                value=default_f,
                min_value=0.0, max_value=120.0, step=0.1, format="%.2f",
                key=f"f_rec_val_{idx}",
            )
        else:
            ov["f_rec_override"] = None

    # ── Per-event reset ───────────────────────────────────────────────────
    if st.button("↩ Reset to auto", key=f"reset_ev_{idx}"):
        overrides[idx] = {
            "v_exit_offset": 0.0, "v_rec_override": None,
            "f_exit_offset": 0.0, "f_rec_override": None,
        }
        st.session_state[f"v_exit_offset_{idx}"] = 0.0
        st.session_state[f"f_exit_offset_{idx}"] = 0.0
        st.session_state[f"v_rec_on_{idx}"] = False
        st.session_state[f"f_rec_on_{idx}"] = False
        st.rerun()


def _render_intersection_footer(overrides):
    """
    Render the Recalculate / Reset All buttons and execute the recalculation
    when the user clicks Recalculate.  Call this once, after all per-event
    controls have been rendered.
    """
    any_override = any(
        ov["v_exit_offset"] != 0.0 or ov["v_rec_override"] is not None
        or ov["f_exit_offset"] != 0.0 or ov["f_rec_override"] is not None
        for ov in overrides.values()
    )

    st.divider()
    btn_col, reset_col = st.columns([3, 1])
    with btn_col:
        recalc = st.button(
            "🔄 Recalculate Compliance",
            type="primary",
            use_container_width=True,
            disabled=not any_override,
            help="Apply adjustments and recompute compliance for all modified events",
        )
    with reset_col:
        reset_all = st.button(
            "Reset All",
            use_container_width=True,
            disabled=not any_override,
        )

    if reset_all:
        for ev_idx in list(overrides.keys()):
            st.session_state[f"v_exit_offset_{ev_idx}"] = 0.0
            st.session_state[f"f_exit_offset_{ev_idx}"] = 0.0
            st.session_state[f"v_rec_on_{ev_idx}"] = False
            st.session_state[f"f_rec_on_{ev_idx}"] = False
        st.session_state["intersection_overrides"] = {}
        st.rerun()

    if recalc:
        df_ev = st.session_state["df_events"].copy()
        cfg   = st.session_state["config"]

        with st.spinner("Recalculating — rebuilding interpolated data..."):
            df_interp = _recompute_df_interp(st.session_state["df_proc"])

        v_upper = cfg.nominal_voltage * (1 + cfg.voltage_tolerance_pct / 100)
        v_lower = cfg.nominal_voltage * (1 - cfg.voltage_tolerance_pct / 100)

        for ev_idx, ov in overrides.items():
            if ev_idx not in df_ev.index:
                continue
            row = df_ev.loc[ev_idx]
            dkw = row.get("dKw", 0)

            # -- Voltage --------------------------------------------------
            v_exit_orig = row.get("V_exit_ts")
            v_exit_adj = (
                pd.Timestamp(v_exit_orig) + pd.Timedelta(seconds=ov["v_exit_offset"])
                if pd.notnull(v_exit_orig) else None
            )
            if v_exit_adj is not None:
                df_ev.at[ev_idx, "V_exit_ts"] = v_exit_adj

            if ov["v_rec_override"] is not None:
                new_v_rec_s = ov["v_rec_override"]
            elif v_exit_adj is not None and ov["v_exit_offset"] != 0.0:
                new_v_rec_s = calculate_recovery_time(
                    df_interp, v_exit_adj, "Avg_Voltage_LL", v_upper, v_lower
                )
            else:
                new_v_rec_s = row.get("V_rec_s")
            df_ev.at[ev_idx, "V_rec_s"] = new_v_rec_s

            # -- Frequency ------------------------------------------------
            f_exit_orig = row.get("F_exit_ts")
            f_exit_adj = (
                pd.Timestamp(f_exit_orig) + pd.Timedelta(seconds=ov["f_exit_offset"])
                if pd.notnull(f_exit_orig) else None
            )
            if f_exit_adj is not None:
                df_ev.at[ev_idx, "F_exit_ts"] = f_exit_adj

            f_upper = cfg.freq_recovery_upper_increase if dkw > 0 else cfg.freq_recovery_upper_decrease
            f_lower = cfg.freq_recovery_lower_increase if dkw > 0 else cfg.freq_recovery_lower_decrease

            if ov["f_rec_override"] is not None:
                new_f_rec_s = ov["f_rec_override"]
            elif f_exit_adj is not None and ov["f_exit_offset"] != 0.0:
                new_f_rec_s = calculate_recovery_time(
                    df_interp, f_exit_adj, "Avg_Frequency", f_upper, f_lower
                )
            else:
                new_f_rec_s = row.get("F_rec_s")
            df_ev.at[ev_idx, "F_rec_s"] = new_f_rec_s

            # -- Re-run compliance ----------------------------------------
            new_compliance = check_compliance(df_ev.loc[ev_idx], cfg)
            df_ev.at[ev_idx, "Compliance_Status"] = new_compliance["Compliance_Status"]
            df_ev.at[ev_idx, "Failure_Reasons"]   = new_compliance["Failure_Reasons"]

        st.session_state["df_events"] = df_ev

        client = st.session_state.get("client_name", "report")
        table_file = os.path.join(IMAGE_DIR, f"{client}_table.png")
        try:
            new_table_path = save_compliance_table_as_image(
                df_ev, table_file,
                client,
                nom_v=cfg.nominal_voltage,
                nom_f=cfg.nominal_frequency,
                rated_load_kw=st.session_state.get("rated_load_kw"),
            )
            st.session_state["table_path"] = new_table_path
        except Exception:
            pass

        # Regenerate snapshot images so updated crossing markers are visible
        try:
            new_snap_paths = generate_all_snapshots(
                st.session_state["df_raw"], df_ev, client,
                output_dir=SNAPSHOT_DIR,
                show_limits=st.session_state.get("show_limits_snapshots", False),
                nom_v=cfg.nominal_voltage,
                nom_f=cfg.nominal_frequency,
                tol_v=cfg.voltage_tolerance_pct,
                tol_f=cfg.frequency_tolerance_pct,
                show_debug=st.session_state.get("show_debug", False),
                rated_load_kw=st.session_state.get("rated_load_kw"),
                window_s=cfg.snapshot_window_s,
            )
            st.session_state["snapshot_paths"] = new_snap_paths
        except Exception:
            pass

        st.success("Compliance recalculated with your adjustments.")
        st.rerun()


# --- Design System ---
# Direction: Industrial Precision — authoritative, data-forward, technical dashboard
# Palette: deep navy sidebar · electric blue accents · clean white surfaces · amber warnings
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Global ── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
.main .block-container {
    padding-top: 1.75rem;
    padding-bottom: 2rem;
    max-width: 1200px;
}

/* ── Sidebar ── */
div[data-testid="stSidebar"] {
    background-color: #0f172a;
    border-right: 1px solid #1e293b;
}
div[data-testid="stSidebar"] * {
    color: #cbd5e1 !important;
}
div[data-testid="stSidebar"] h1 {
    font-size: 1.1rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.05em !important;
    text-transform: uppercase !important;
    color: #f1f5f9 !important;
}
div[data-testid="stSidebar"] h2,
div[data-testid="stSidebar"] h3 {
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: #64748b !important;
    margin-top: 0.25rem !important;
    margin-bottom: 0.5rem !important;
}
div[data-testid="stSidebar"] label,
div[data-testid="stSidebar"] .stCheckbox label {
    font-size: 0.8rem !important;
    color: #94a3b8 !important;
}
div[data-testid="stSidebar"] hr {
    border-color: #1e293b !important;
    margin: 0.75rem 0 !important;
}
div[data-testid="stSidebar"] input,
div[data-testid="stSidebar"] .stNumberInput input,
div[data-testid="stSidebar"] .stTextInput input {
    background-color: #1e293b !important;
    border: 1px solid #334155 !important;
    color: #e2e8f0 !important;
    border-radius: 6px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.8rem !important;
}
div[data-testid="stSidebar"] .stSelectbox > div > div {
    background-color: #1e293b !important;
    border: 1px solid #334155 !important;
    color: #e2e8f0 !important;
    border-radius: 6px !important;
}

/* ── Primary buttons ── */
div[data-testid="stSidebar"] .stButton > button[kind="primary"],
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 100%) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.02em !important;
    box-shadow: 0 1px 3px rgba(37,99,235,0.3) !important;
    transition: all 0.15s ease !important;
}
div[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover,
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #1e40af 0%, #1d4ed8 100%) !important;
    box-shadow: 0 4px 12px rgba(37,99,235,0.4) !important;
}
div[data-testid="stSidebar"] .stButton > button:not([kind="primary"]) {
    background-color: #1e293b !important;
    color: #94a3b8 !important;
    border: 1px solid #334155 !important;
    border-radius: 5px !important;
    font-size: 0.75rem !important;
}

/* ── Download buttons ── */
div[data-testid="stSidebar"] .stDownloadButton > button {
    background-color: #1e293b !important;
    color: #7dd3fc !important;
    border: 1px solid #334155 !important;
    border-radius: 6px !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
}
div[data-testid="stSidebar"] .stDownloadButton > button:hover {
    background-color: #0f4c81 !important;
    border-color: #2563eb !important;
}

/* ── Main area headings ── */
.main h1 {
    font-size: 1.75rem;
    font-weight: 700;
    color: #0f172a;
    letter-spacing: -0.02em;
    border-bottom: 2px solid #2563eb;
    padding-bottom: 0.4rem;
    margin-bottom: 1.25rem;
}
.main h2 {
    font-size: 1.15rem;
    font-weight: 600;
    color: #1e293b;
    letter-spacing: -0.01em;
    margin-top: 1.5rem;
    margin-bottom: 0.75rem;
}

/* ── Metric cards ── */
div[data-testid="stMetric"] {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 1rem 1.25rem !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.15);
}
div[data-testid="stMetric"] label {
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: #64748b !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 1.6rem !important;
    font-weight: 700 !important;
    color: #f1f5f9 !important;
}

/* ── Expanders ── */
.stExpander {
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
    overflow: hidden !important;
}
.stExpander summary {
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    color: #1e293b !important;
}

/* ── Dataframe ── */
.stDataFrame {
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
    overflow: hidden !important;
}

/* ── Alert / info boxes ── */
.stAlert {
    border-radius: 8px !important;
    font-size: 0.875rem !important;
}

/* ── Status / spinner text ── */
.stStatus {
    border-radius: 8px !important;
    font-size: 0.85rem !important;
}

/* ── Caption / small text ── */
.stCaption, small {
    color: #64748b !important;
    font-size: 0.75rem !important;
}

/* ── Code blocks in debug log ── */
.stCodeBlock {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.72rem !important;
}
</style>
""", unsafe_allow_html=True)


def _parse_hms(s: str) -> datetime.time:
    """Parse 'HH:MM:SS' → datetime.time. Raises ValueError on bad input."""
    parts = [int(x) for x in s.strip().split(":")]
    return datetime.time(*parts)


# Session-state keys used by the time-filter sync callbacks.
# Fixed strings so module-level callbacks can reference them safely.
_TF_START_TEXT = "tf_start_text"
_TF_END_TEXT   = "tf_end_text"
_TF_START_SLIDER = "tf_start_slider"
_TF_END_SLIDER   = "tf_end_slider"


def _on_start_slider():
    """on_change for the start slider — pushes new value into the text field."""
    v = st.session_state.get(_TF_START_SLIDER)
    if v is not None:
        st.session_state[_TF_START_TEXT] = v.strftime("%H:%M:%S")


def _on_end_slider():
    """on_change for the end slider — pushes new value into the text field."""
    v = st.session_state.get(_TF_END_SLIDER)
    if v is not None:
        st.session_state[_TF_END_TEXT] = v.strftime("%H:%M:%S")


def _get_csv_time_range(path):
    """Read a CSV file path and return (start_str, end_str) or (None, None)."""
    try:
        temp_df = load_and_prepare_csv(path)
        if not temp_df.empty:
            return (
                temp_df["Timestamp"].min().strftime("%H:%M:%S"),
                temp_df["Timestamp"].max().strftime("%H:%M:%S"),
            )
    except Exception:
        pass
    return (None, None)


# nom_v and nom_f are set by the sidebar Display Options section below.

# ── Cold-start: load persisted settings into session state ────────────────────
if "_ds" not in st.session_state:
    _loaded = _load_dev_settings()
    st.session_state["_ds"] = _loaded
    # Pre-populate keyed widgets that have NO value= parameter (safe — no conflict).
    # Widgets with key= + value= are handled by passing value=_ds.get(...) instead.
    for _k in ("fri_upper", "fri_lower", "frd_upper", "frd_lower",
                "nom_v_preset", "nom_v_custom", "rated_load_input", "report_format"):
        if _k not in st.session_state:
            st.session_state[_k] = _loaded.get(_k, _DEV_DEFAULTS[_k])
    # Time filter: restore only if the saved CSV path still matches
    if _loaded.get("_tf_csv_path"):
        st.session_state["_tf_csv_path"] = _loaded["_tf_csv_path"]
        st.session_state[_TF_START_TEXT] = _loaded.get("tf_start_text", "")
        st.session_state[_TF_END_TEXT]   = _loaded.get("tf_end_text", "")
_ds: dict = st.session_state["_ds"]  # shorthand used throughout the sidebar
# ─────────────────────────────────────────────────────────────────────────────


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.title("\u2699\ufe0f Configuration")

    # ── Dev Mode ──────────────────────────────────────────────
    with st.expander("🛠 Dev Mode", expanded=_ds.get("dev_mode", False)):
        dev_mode = st.checkbox(
            "Persist settings across restarts",
            value=_ds.get("dev_mode", False),
            help="Saves all sidebar settings to uploads/dev_settings.json on every run.",
        )
        _ds["dev_mode"] = dev_mode
        if dev_mode:
            st.caption("Settings auto-saved to `uploads/dev_settings.json`")
        if st.button("Reset all settings to defaults", use_container_width=True):
            if os.path.exists(DEV_SETTINGS_FILE):
                os.remove(DEV_SETTINGS_FILE)
            st.session_state.pop("_ds", None)
            st.rerun()

    st.divider()

    # ── 1. CSV Upload ──────────────────────────────────────────
    st.subheader("Data Files")
    new_csvs = st.file_uploader(
        "Upload CSV files",
        type=["csv"],
        accept_multiple_files=True,
        help="Files are saved locally — no need to re-upload each session.",
    )
    if new_csvs:
        _saved, _failed = [], []
        for f in new_csvs:
            dest = os.path.join(UPLOADS_CSV_DIR, f.name)
            try:
                f.seek(0)
                with open(dest, "wb") as out:
                    out.write(f.read())
                _saved.append(f.name)
                log.info(f"CSV saved: {dest}")
            except Exception as e:
                _failed.append(f.name)
                log.error(f"Failed to save CSV {f.name}: {e}")
        if _saved:
            st.toast(f"Saved: {', '.join(_saved)}", icon="✅")
        if _failed:
            st.error(f"Failed to save: {', '.join(_failed)} — check Debug Log")
        # No st.rerun() — files are saved before saved_csvs is built below,
        # so they appear in the dropdown immediately on this render pass.

    saved_csvs = sorted(glob.glob(os.path.join(UPLOADS_CSV_DIR, "*.csv")))

    # Show saved files with size and remove button
    for csv_path in saved_csvs:
        fname = os.path.basename(csv_path)
        size = os.path.getsize(csv_path)
        size_str = f"{size/1024:.1f}KB" if size < 1024*1024 else f"{size/1024/1024:.1f}MB"
        c1, c2 = st.columns([5, 1])
        c1.markdown(f"📊 **{fname}**  \n<small>{size_str}</small>", unsafe_allow_html=True)
        if c2.button("✕", key=f"rm_csv_{fname}", help=f"Remove {fname}"):
            os.remove(csv_path)
            st.rerun()

    saved_csvs = sorted(glob.glob(os.path.join(UPLOADS_CSV_DIR, "*.csv")))
    all_csv_names = [os.path.basename(p) for p in saved_csvs]

    selected_csv_path = None
    client_name = ""
    auto_start = ""
    auto_end = ""

    if all_csv_names:
        _saved_csv = _ds.get("selected_csv_name", "")
        _csv_idx = all_csv_names.index(_saved_csv) if _saved_csv in all_csv_names else 0
        selected_name = st.selectbox("Select CSV to analyse", all_csv_names, index=_csv_idx)
        _ds["selected_csv_name"] = selected_name
        selected_csv_path = os.path.join(UPLOADS_CSV_DIR, selected_name)
        client_name = os.path.splitext(selected_name)[0]
        auto_start, auto_end = _get_csv_time_range(selected_csv_path)

    st.divider()

    # ── 2. Acceptance Criteria ────────────────────────────────
    st.subheader("Acceptance Criteria")
    apply_iso = st.checkbox("Apply ISO 8528 Presets", value=_ds.get("apply_iso", False))
    show_limits = st.checkbox("Show Limits on Graphs", value=_ds.get("show_limits", False))
    show_limits_snapshots = st.checkbox("Show Limits on Snapshots", value=_ds.get("show_limits_snapshots", False))
    show_debug = st.checkbox("Show Event Detection (De-bugging)", value=_ds.get("show_debug", False))
    detection_window = st.number_input(
        "Detection Window (s)",
        value=float(_ds.get("detection_window", 5.0)),
        min_value=1.0, max_value=30.0, step=1.0,
        help="Time window used to group consecutive load step rows into a single event.",
    )
    snapshot_window = st.number_input(
        "Snapshot Window (s)",
        value=float(_ds.get("snapshot_window", 10.0)),
        min_value=3.0, max_value=60.0, step=1.0,
        help="Seconds shown either side of each event in snapshots. Also sets the window used to find peak voltage/frequency deviation.",
    )
    _ds["apply_iso"] = apply_iso
    _ds["show_limits"] = show_limits
    _ds["show_limits_snapshots"] = show_limits_snapshots
    _ds["show_debug"] = show_debug
    _ds["detection_window"] = detection_window
    _ds["snapshot_window"] = snapshot_window

    if apply_iso:
        load_thresh = 50.0; v_tol = 1.0; v_rec = 4.0; v_max_dev = 15.0
        f_tol = 0.5; f_rec = 3.0; f_max_dev = 7.0
    else:
        load_thresh = float(_ds.get("load_thresh", 50.0))
        v_tol      = float(_ds.get("v_tol", 1.0))
        v_rec      = float(_ds.get("v_rec", 4.0))
        v_max_dev  = float(_ds.get("v_max_dev", 15.0))
        f_tol      = float(_ds.get("f_tol", 0.5))
        f_rec      = float(_ds.get("f_rec", 3.0))
        f_max_dev  = float(_ds.get("f_max_dev", 7.0))

    col1, col2 = st.columns(2)
    with col1:
        load_thresh = st.number_input("Load Threshold (kW)", value=load_thresh, min_value=0.0, step=10.0, disabled=apply_iso)
        v_tol = st.number_input("Voltage Tolerance (%)", value=v_tol, min_value=0.0, step=0.5, disabled=apply_iso)
        v_rec = st.number_input("Voltage Recovery (s)", value=v_rec, min_value=0.0, step=0.5, disabled=apply_iso)
        v_max_dev = st.number_input("Max Voltage Dev (%)", value=v_max_dev, min_value=0.0, step=1.0, disabled=apply_iso)
    with col2:
        f_tol = st.number_input("Frequency Tolerance (%)", value=f_tol, min_value=0.0, step=0.1, disabled=apply_iso)
        f_rec = st.number_input("Frequency Recovery (s)", value=f_rec, min_value=0.0, step=0.5, disabled=apply_iso)
        f_max_dev = st.number_input("Max Frequency Dev (%)", value=f_max_dev, min_value=0.0, step=1.0, disabled=apply_iso)

    if not apply_iso:
        _ds["load_thresh"] = load_thresh; _ds["v_tol"] = v_tol
        _ds["v_rec"] = v_rec;             _ds["v_max_dev"] = v_max_dev
        _ds["f_tol"] = f_tol;             _ds["f_rec"] = f_rec
        _ds["f_max_dev"] = f_max_dev

    st.markdown("**Frequency Recovery Bands (Hz)**")
    col_fi, col_fd = st.columns(2)
    with col_fi:
        st.caption("Load Increase")
        # No value= — session_state pre-populated from _ds on cold start
        f_rec_upper_inc = st.number_input("Upper (Hz)", min_value=0.0, step=0.05, format="%.2f", key="fri_upper", disabled=apply_iso)
        f_rec_lower_inc = st.number_input("Lower (Hz)", min_value=0.0, step=0.05, format="%.2f", key="fri_lower", disabled=apply_iso)
    with col_fd:
        st.caption("Load Decrease")
        f_rec_upper_dec = st.number_input("Upper (Hz)", min_value=0.0, step=0.05, format="%.2f", key="frd_upper", disabled=apply_iso)
        f_rec_lower_dec = st.number_input("Lower (Hz)", min_value=0.0, step=0.05, format="%.2f", key="frd_lower", disabled=apply_iso)

    st.divider()

    # ── Rated Load ────────────────────────────────────────────
    # No value= — session_state["rated_load_input"] pre-populated from _ds on cold start
    rated_load_str = st.text_input(
        "Rated Load (kW)",
        help="Optional. When set, load change % is calculated against this value.",
        key="rated_load_input",
    )
    st.session_state["rated_load_str"] = rated_load_str
    try:
        rated_load_kw = float(rated_load_str) if rated_load_str.strip() else None
    except ValueError:
        st.warning("Rated Load must be a number.")
        rated_load_kw = None
    st.session_state["rated_load_kw"] = rated_load_kw

    st.divider()

    # ── 4. Display Options ────────────────────────────────────
    st.subheader("Display Options")

    _VOLTAGE_PRESETS = {
        "415 V  (LV — AU/UK)":  415.0,
        "690 V  (MV-LV)":       690.0,
        "11 000 V  (11 kV)":    11000.0,
        "Custom":               None,
    }
    _preset_keys = list(_VOLTAGE_PRESETS.keys())
    # No index= — session_state["nom_v_preset"] is pre-populated from _ds on cold start
    nom_v_preset = st.selectbox("Nominal Voltage", _preset_keys, key="nom_v_preset")
    if _VOLTAGE_PRESETS[nom_v_preset] is None:
        # No value= — session_state["nom_v_custom"] is pre-populated from _ds on cold start
        nom_v = st.number_input("Custom Nominal Voltage (V L-L)", min_value=1.0, step=1.0, key="nom_v_custom")
    else:
        nom_v = _VOLTAGE_PRESETS[nom_v_preset]

    nom_f = st.number_input("Nominal Frequency (Hz)", value=float(_ds.get("nom_f", 50.0)), min_value=1.0, step=0.5)
    _ds["nom_f"] = nom_f

    _csv_voltage_options = [
        "Auto-detect (by column names)",
        "Line-to-Line — use as-is",
        "Line-to-Neutral — convert ×√3 to L-L",
    ]
    _csv_v_mode_map = {
        "Auto-detect (by column names)":        "auto",
        "Line-to-Line — use as-is":             "force_ll",
        "Line-to-Neutral — convert ×√3 to L-L": "force_ln",
    }
    _saved_csv_vtype = _ds.get("csv_voltage_type", _csv_voltage_options[0])
    _csv_v_idx = _csv_voltage_options.index(_saved_csv_vtype) if _saved_csv_vtype in _csv_voltage_options else 0
    csv_voltage_type = st.radio(
        "CSV Voltage Columns",
        _csv_voltage_options,
        index=_csv_v_idx,
        help=(
            "Auto-detect uses column names: U12/U23/U31 = L-L, U1/U2/U3 = L-N.\n"
            "Override if your logger uses non-standard names."
        ),
    )
    _ds["csv_voltage_type"] = csv_voltage_type
    ln_to_ll_mode = _csv_v_mode_map[csv_voltage_type]

    st.divider()

    # ── 5. Time Filter ────────────────────────────────────────
    st.subheader("Time Filter")

    # Reset displayed text whenever the selected CSV changes
    if st.session_state.get("_tf_csv_path") != selected_csv_path:
        st.session_state["_tf_csv_path"] = selected_csv_path
        st.session_state[_TF_START_TEXT] = auto_start or ""
        st.session_state[_TF_END_TEXT]   = auto_end or ""

    # Text inputs driven by session state — updated by slider on_change callbacks
    start_time_text = st.text_input("Start Time", key=_TF_START_TEXT, placeholder="HH:MM:SS")
    end_time_text   = st.text_input("End Time",   key=_TF_END_TEXT,   placeholder="HH:MM:SS")

    start_time = start_time_text
    end_time   = end_time_text

    if auto_start and auto_end:
        try:
            t_min = _parse_hms(auto_start)
            t_max = _parse_hms(auto_end)

            try:    t_start_val = _parse_hms(start_time_text) if start_time_text else t_min
            except: t_start_val = t_min
            try:    t_end_val = _parse_hms(end_time_text) if end_time_text else t_max
            except: t_end_val = t_max

            t_start_val = max(t_min, min(t_max, t_start_val))
            t_end_val   = max(t_min, min(t_max, t_end_val))

            start_slider = st.slider(
                "Start", min_value=t_min, max_value=t_max, value=t_start_val,
                format="HH:mm:ss", step=datetime.timedelta(seconds=2),
                label_visibility="collapsed",
                key=_TF_START_SLIDER,
                on_change=_on_start_slider,
            )
            end_slider = st.slider(
                "End", min_value=t_min, max_value=t_max, value=t_end_val,
                format="HH:mm:ss", step=datetime.timedelta(seconds=2),
                label_visibility="collapsed",
                key=_TF_END_SLIDER,
                on_change=_on_end_slider,
            )
            start_time = start_slider.strftime("%H:%M:%S")
            end_time = end_slider.strftime("%H:%M:%S")
        except Exception:
            pass

    st.divider()

    # ── 5. Run Analysis ───────────────────────────────────────
    run_clicked = False
    if selected_csv_path is not None:
        run_clicked = st.button("\u26a1 Run Analysis", type="primary", use_container_width=True)
    else:
        st.info("Upload CSV files above to begin.")

    st.divider()

    # ── 6. Report Details ─────────────────────────────────────
    st.subheader("Report Details")
    report_title = st.text_input("Report Title", value=client_name, placeholder="Enter report/client name")
    gen_sn = st.text_input("Generator Serial Number", value=_ds.get("gen_sn", ""), placeholder="Enter Gen S/N")
    site_address = st.text_input("Site Address", value=_ds.get("site_address", ""), placeholder="Enter site address")
    custom_text = st.text_input("Custom Text Field", value=_ds.get("custom_text", ""), placeholder="Enter custom info")
    _ds["gen_sn"] = gen_sn
    _ds["site_address"] = site_address
    _ds["custom_text"] = custom_text

    st.divider()

    # ── 7. Report Generation ──────────────────────────────────
    st.subheader("Generate Report")

    report_format = st.radio(
        "Report Format",
        ["Word Template", "HTML Template"],
        horizontal=True,
        key="report_format",
    )

    selected_template_path = None
    html_template_str = None

    if report_format == "Word Template":
        new_templates = st.file_uploader(
            "Upload Word Templates (.docx)",
            type=["docx"],
            accept_multiple_files=True,
            help="Files are saved locally — no need to re-upload each session.",
        )
        if new_templates:
            for f in new_templates:
                dest = os.path.join(UPLOADS_TEMPLATE_DIR, f.name)
                try:
                    f.seek(0)
                    with open(dest, "wb") as out:
                        out.write(f.read())
                    log.info(f"Template saved: {dest}")
                except Exception as e:
                    log.error(f"Failed to save template {f.name}: {e}")
                    st.error(f"Failed to save {f.name} — check Debug Log")

        saved_templates = sorted(glob.glob(os.path.join(UPLOADS_TEMPLATE_DIR, "*.docx")))

        for tpl_path in saved_templates:
            fname = os.path.basename(tpl_path)
            size = os.path.getsize(tpl_path)
            size_str = f"{size/1024:.1f}KB" if size < 1024*1024 else f"{size/1024/1024:.1f}MB"
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"📄 **{fname}**  \n<small>{size_str}</small>", unsafe_allow_html=True)
            if c2.button("✕", key=f"rm_tpl_{fname}", help=f"Remove {fname}"):
                os.remove(tpl_path)
                st.rerun()

        saved_templates = sorted(glob.glob(os.path.join(UPLOADS_TEMPLATE_DIR, "*.docx")))
        all_template_names = [os.path.basename(p) for p in saved_templates]

        if all_template_names:
            selected_template_name = st.selectbox("Select Template", all_template_names)
            selected_template_path = os.path.join(UPLOADS_TEMPLATE_DIR, selected_template_name)

            with st.expander("Available Placeholders"):
                st.markdown("""
`{{Avg_Voltage_LL}}` `{{Avg_kW}}` `{{Avg_Current}}`
`{{Avg_Frequency}}` `{{Avg_THD_F}}` `{{Avg_PF}}`
`{{Compliance_Table}}`
`{{Snapshot_1}}` `{{Snapshot_2}}` ...
`{{Report_Title}}` `{{Gen_SN}}` `{{Site_Address}}`
`{{Custom_Field}}` `{{Date}}` `{{Start Time}}` `{{End Time}}`
                """)

    else:  # HTML Template
        st.caption("Edit the HTML template below. Use {{placeholders}} for dynamic content.")

        if "html_template" not in st.session_state:
            st.session_state["html_template"] = get_default_template()

        col_reset, _ = st.columns([1, 2])
        if col_reset.button("↺ Reset to Default", key="reset_html_template"):
            st.session_state["html_template"] = get_default_template()
            st.rerun()

        st.session_state["html_template"] = st.text_area(
            "HTML Template",
            value=st.session_state["html_template"],
            height=300,
            key="html_template_editor",
            label_visibility="collapsed",
        )
        html_template_str = st.session_state["html_template"]

        with st.expander("Available Placeholders"):
            st.markdown("""
`{{Avg_Voltage_LL}}` `{{Avg_kW}}` `{{Avg_Current}}`
`{{Avg_Frequency}}` `{{Avg_THD_F}}` `{{Avg_PF}}`
`{{Compliance_Table}}`
`{{Snapshot_1}}` `{{Snapshot_2}}` ... `{{Snapshot_10}}`
`{{Report_Title}}` `{{Gen_SN}}` `{{Site_Address}}`
`{{Custom_Field}}` `{{Date}}` `{{Start Time}}` `{{End Time}}`
            """)
        st.caption("PDF: WeasyPrint (Cloud) → LibreOffice → reportlab fallback.")

    report_filename = st.text_input(
        "Report Filename",
        value=client_name or "PQA_Report",
        placeholder="Enter filename (no extension)",
    )

    with st.expander("⬇️ Download Options"):
        if report_format == "Word Template":
            download_format = st.selectbox(
                "Download Format",
                ["Word (.docx)", "PDF", "Both"],
            )
        else:
            download_format = st.selectbox(
                "Download Format",
                ["HTML", "PDF", "Both"],
            )

    generate_clicked = False
    analysis_ready = st.session_state.get("analysis_done")
    if report_format == "Word Template":
        if selected_template_path is not None and analysis_ready:
            generate_clicked = st.button("\U0001f4c4 Generate Report", type="primary", use_container_width=True)
        elif not analysis_ready:
            st.caption("Run analysis first to enable report generation.")
        else:
            st.caption("Upload a template above to generate a report.")
    else:  # HTML Template
        if analysis_ready:
            generate_clicked = st.button("\U0001f4c4 Generate Report", type="primary", use_container_width=True)
        else:
            st.caption("Run analysis first to enable report generation.")

    # ── Generated Reports List (sidebar) ──────────────────────
    sidebar_reports = st.session_state.get("generated_reports", [])
    if sidebar_reports:
        st.divider()
        st.subheader("Generated Reports")
        for i, entry in enumerate(sidebar_reports):
            st.markdown(f"**{entry['name']}**")
            c1, c2 = st.columns(2)
            if "docx" in entry["files"]:
                c1.download_button(
                    "⬇ .docx",
                    data=bytes(entry["files"]["docx"]),
                    file_name=f"{entry['name']}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"sb_dl_docx_{i}",
                    use_container_width=True,
                )
            elif "html" in entry["files"]:
                c1.download_button(
                    "⬇ .html",
                    data=bytes(entry["files"]["html"]),
                    file_name=f"{entry['name']}.html",
                    mime="text/html",
                    key=f"sb_dl_html_{i}",
                    use_container_width=True,
                )
            if "pdf" in entry["files"]:
                c2.download_button(
                    "⬇ .pdf",
                    data=bytes(entry["files"]["pdf"]),
                    file_name=f"{entry['name']}.pdf",
                    mime="application/pdf",
                    key=f"sb_dl_pdf_{i}",
                    use_container_width=True,
                )
            elif "docx" in entry["files"] or "html" in entry["files"]:
                c2.caption("PDF n/a")

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for entry in sidebar_reports:
                if "docx" in entry["files"]:
                    zipf.writestr(f"{entry['name']}.docx", bytes(entry["files"]["docx"]))
                if "html" in entry["files"]:
                    zipf.writestr(f"{entry['name']}.html", bytes(entry["files"]["html"]))
                if "pdf" in entry["files"]:
                    zipf.writestr(f"{entry['name']}.pdf", bytes(entry["files"]["pdf"]))
        st.download_button(
            "⬇️ Download All Reports",
            data=zip_buffer.getvalue(),
            file_name="PQA_Reports.zip",
            mime="application/zip",
            use_container_width=True,
        )


# ============================================================
# MAIN AREA
# ============================================================
st.title("\u26a1 Power Quality Analysis")

if selected_csv_path is not None:
    with st.expander("Preview uploaded data", expanded=False):
        preview_df = pd.read_csv(selected_csv_path, sep=None, engine="python", nrows=10)
        st.dataframe(preview_df, width="stretch")

    if auto_start and auto_end:
        st.caption(f"Detected time range: **{auto_start}** to **{auto_end}**")

    # ── Run Analysis ──────────────────────────────────────────
    if run_clicked:
        init_output_dirs()

        config = AnalysisConfig(
            nominal_voltage=nom_v,
            nominal_frequency=nom_f,
            load_threshold_kw=load_thresh,
            voltage_tolerance_pct=v_tol,
            voltage_recovery_time_s=v_rec,
            voltage_max_deviation_pct=v_max_dev,
            frequency_tolerance_pct=f_tol,
            frequency_recovery_time_s=f_rec,
            frequency_max_deviation_pct=f_max_dev,
            freq_recovery_upper_increase=f_rec_upper_inc,
            freq_recovery_lower_increase=f_rec_lower_inc,
            freq_recovery_upper_decrease=f_rec_upper_dec,
            freq_recovery_lower_decrease=f_rec_lower_dec,
            detection_window_s=detection_window,
            snapshot_window_s=snapshot_window,
            ln_to_ll_mode=ln_to_ll_mode,
        )

        try:
            log.info(f"Run Analysis clicked — CSV: {selected_csv_path}, time: {start_time}–{end_time}")
            with st.spinner("Loading and processing data..."):
                df_raw = load_and_prepare_csv(selected_csv_path, start_time=start_time, end_time=end_time)
                if df_raw.empty:
                    log.warning("CSV loaded but no rows after time filter.")
                    st.error("No data found. Check your CSV and time range.")
                    st.stop()
                log.info(f"CSV loaded: {len(df_raw)} rows")
                df_proc, df_events = perform_analysis(df_raw, config)
                log.info(f"Analysis done: {len(df_events)} events detected")
        except Exception:
            log.exception("perform_analysis failed")
            st.error("Analysis failed — see Debug Log in the sidebar for details.")
            st.stop()

        st.session_state.update({
            "df_raw": df_raw,
            "df_proc": df_proc,
            "df_events": df_events,
            "client_name": client_name,
            "config": config,
            "analysis_done": True,
            "generated_reports": st.session_state.get("generated_reports", []),
            "intersection_overrides": {},   # clear any overrides from previous run
            "show_debug": show_debug,
            "show_limits_snapshots": show_limits_snapshots,
        })

        mcol1, mcol2, mcol3, mcol4 = st.columns(4)
        with mcol1: st.metric("Data Points", f"{len(df_proc):,}")
        with mcol2: st.metric("Events Detected", f"{len(df_events)}")
        with mcol3:
            if not df_events.empty and "Compliance_Status" in df_events.columns:
                st.metric("Pass", f"{(df_events['Compliance_Status']=='Pass').sum()}/{len(df_events)}")
        with mcol4:
            if not df_events.empty and "Compliance_Status" in df_events.columns:
                st.metric("Fail", f"{(df_events['Compliance_Status']=='Fail').sum()}/{len(df_events)}")

        # Main time-series graphs are always clean — debug overlays live on snapshots only.
        plot_kwargs = dict(
            output_dir=GRAPH_DIR, show_limits=show_limits,
            nom_v=nom_v, nom_f=nom_f, tol_v=v_tol, tol_f=f_tol,
            show_debug=False,
            df_events=None,
            thresh_kw=load_thresh,
        )
        try:
            with st.spinner("Generating voltage plot..."):
                graph_paths = generate_plots(df_proc, client_name, metric_keys=["Avg_Voltage_LL"], **plot_kwargs)
            st.session_state["graph_paths"] = graph_paths
            log.info("Voltage plot generated")

            with st.spinner("Generating remaining plots..."):
                other_paths = generate_plots(
                    df_proc, client_name,
                    metric_keys=["Avg_kW", "Avg_Current", "Avg_Frequency", "Avg_PF", "Avg_THD_F"],
                    **plot_kwargs,
                )
                graph_paths.update(other_paths)
            st.session_state["graph_paths"] = graph_paths
            log.info(f"All plots generated: {list(graph_paths.keys())}")
        except Exception:
            log.exception("Plot generation failed")
            st.warning("Plot generation failed — see Debug Log.")

        snapshot_paths = []
        table_path = None
        if not df_events.empty:
            try:
                with st.spinner("Generating compliance table..."):
                    table_file = os.path.join(IMAGE_DIR, f"{client_name}_table.png")
                    table_path = save_compliance_table_as_image(
                        df_events, table_file,
                        client_name,
                        nom_v=nom_v, nom_f=nom_f,
                        rated_load_kw=rated_load_kw,
                    )
                log.info(f"Compliance table saved: {table_path}")
            except Exception:
                log.exception("Compliance table generation failed")
            try:
                with st.spinner("Generating event snapshots..."):
                    snapshot_paths = generate_all_snapshots(
                        df_raw, df_events, client_name, output_dir=SNAPSHOT_DIR,
                        show_limits=show_limits_snapshots,
                        nom_v=nom_v, nom_f=nom_f, tol_v=v_tol, tol_f=f_tol,
                        show_debug=show_debug,
                        rated_load_kw=rated_load_kw,
                        window_s=snapshot_window,
                    )
                log.info(f"{len(snapshot_paths)} snapshots generated")
            except Exception:
                log.exception("Snapshot generation failed")
        else:
            st.warning("No load events detected above the threshold.")

        st.session_state["snapshot_paths"] = snapshot_paths
        st.session_state["table_path"] = table_path
        st.success(f"Analysis complete — {len(df_events)} events, {len(graph_paths)} plots, {len(snapshot_paths)} snapshots.")

else:
    st.info("Upload CSV files in the sidebar to get started.")


# ============================================================
# RESULTS
# ============================================================
if st.session_state.get("analysis_done"):
    df_events = st.session_state["df_events"]
    graph_paths = st.session_state.get("graph_paths", {})
    snapshot_paths = st.session_state.get("snapshot_paths", [])
    table_path = st.session_state.get("table_path")
    client_name_display = st.session_state["client_name"]
    config = st.session_state["config"]

    # Compliance Table
    if not df_events.empty:
        st.header("Compliance Results")

        nom_v = config.nominal_voltage
        nom_f = config.nominal_frequency
        rated_load_kw = st.session_state.get("rated_load_kw")

        # Build display frame — same ordering and detail as the SVG report table.
        src = df_events
        disp = pd.DataFrame()

        # Event Time
        if "Timestamp" in src.columns:
            def _fmt_ts(row):
                s = row["Timestamp"]
                e = row.get("End_Timestamp", s)
                if pd.isna(e) or s == e:
                    return s.strftime("%H:%M:%S")
                return s.strftime("%H:%M:%S") + f"–{e.strftime('%H:%M:%S')}"
            disp["Event Time"] = src.apply(_fmt_ts, axis=1)

        # Load Change
        if "dKw" in src.columns:
            dkw = pd.to_numeric(src["dKw"], errors="coerce")
            def _fmt_dkw(x):
                if pd.isnull(x):
                    return "—"
                line1 = f"{x:+,.1f} kW"
                if rated_load_kw and rated_load_kw > 0:
                    return f"{line1}<br><small>({x / rated_load_kw * 100:+.1f}% rated)</small>"
                return line1
            disp["Load Change"] = dkw.map(_fmt_dkw)

        # Voltage Deviation — V_dev is the actual measured voltage (V)
        if "V_dev" in src.columns:
            v_dev = pd.to_numeric(src["V_dev"], errors="coerce")
            disp["Voltage Deviation"] = v_dev.map(
                lambda x: f"{x:.1f} V<br><small>({(x - nom_v) / nom_v * 100:+.2f}%)</small>"
                if pd.notnull(x) else "—"
            )

        # Voltage Recovery
        if "V_rec_s" in src.columns:
            disp["Voltage Recovery"] = pd.to_numeric(src["V_rec_s"], errors="coerce").map(
                lambda x: f"{x:.2f} s" if pd.notnull(x) else "—"
            )

        # Frequency Deviation — F_dev is the actual measured frequency (Hz)
        if "F_dev" in src.columns:
            f_dev = pd.to_numeric(src["F_dev"], errors="coerce")
            disp["Frequency Deviation"] = f_dev.map(
                lambda x: f"{x:.3f} Hz<br><small>({(x - nom_f) / nom_f * 100:+.2f}%)</small>"
                if pd.notnull(x) else "—"
            )

        # Frequency Recovery
        if "F_rec_s" in src.columns:
            disp["Frequency Recovery"] = pd.to_numeric(src["F_rec_s"], errors="coerce").map(
                lambda x: f"{x:.2f} s" if pd.notnull(x) else "—"
            )

        # Compliance Status
        if "Compliance_Status" in src.columns:
            disp["Compliance Status"] = src["Compliance_Status"]

        # Failure Reasons
        if "Failure_Reasons" in src.columns:
            disp["Failure Reasons"] = src["Failure_Reasons"].fillna("").astype(str).str.replace(";", "<br>")

        def _render_compliance_html(df):
            cols = list(df.columns)
            header = "".join(f"<th>{c}</th>" for c in cols)
            rows_html = []
            for _, row in df.iterrows():
                cells = []
                for c, v in zip(cols, row):
                    v = "" if str(v) in ("nan", "None") else str(v)
                    if c == "Compliance Status":
                        color = "#16a34a" if v == "Pass" else "#dc2626"
                        cells.append(f'<td style="color:{color};font-weight:600">{v}</td>')
                    else:
                        cells.append(f"<td>{v}</td>")
                rows_html.append(f"<tr>{''.join(cells)}</tr>")
            table_rows = "\n".join(rows_html)
            return f"""
            <style>
              .pqa-table {{
                width: 100%; border-collapse: collapse;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                font-size: 14px; color: #111827;
              }}
              .pqa-table th {{
                background: #f9fafb; font-weight: 500; color: #374151;
                padding: 10px 14px; text-align: left;
                border: 1px solid #e5e7eb; white-space: nowrap;
              }}
              .pqa-table td {{
                padding: 10px 14px; border: 1px solid #e5e7eb;
                background: #ffffff; vertical-align: top; line-height: 1.5;
              }}
              .pqa-table td small {{ color: #6b7280; font-size: 12px; }}
              .pqa-table tr:hover td {{ background: #f9fafb; }}
            </style>
            <table class="pqa-table">
              <thead><tr>{header}</tr></thead>
              <tbody>{table_rows}</tbody>
            </table>
            """

        table_height = 100 + len(disp) * 56
        st.components.v1.html(_render_compliance_html(disp), height=table_height, scrolling=False)
        if table_path and os.path.exists(table_path):
            with st.expander("View Compliance Table Image"):
                with open(table_path, "r", encoding="utf-8") as _svg_f:
                    _svg_content = _svg_f.read()
                st.components.v1.html(
                    f'<div style="overflow-x:auto;background:#fff">{_svg_content}</div>',
                    height=600, scrolling=True,
                )

    # Time-Series Plots
    st.header("Time-Series Plots")
    if graph_paths:
        tabs = st.tabs([n.replace("Avg_", "").replace("_", " ") for n in graph_paths.keys()])
        for tab, (name, path) in zip(tabs, graph_paths.items()):
            with tab:
                if path.endswith(".svg"):
                    import re as _re
                    with open(path, "r", encoding="utf-8") as _f:
                        _svg = _f.read()
                    # Strip fixed pixel dimensions so the SVG fills container width
                    # and the browser calculates height from the viewBox aspect ratio.
                    _svg = _re.sub(r'(<svg\b[^>]*?)\s+width="[^"]*"', r'\1 width="100%"', _svg, count=1)
                    _svg = _re.sub(r'(<svg\b[^>]*?)\s+height="[^"]*"', r'\1', _svg, count=1)
                    st.components.v1.html(
                        f'<div style="width:100%">{_svg}</div>',
                        height=480,
                    )
                else:
                    st.image(path, use_container_width=True)
    else:
        st.info("No plots generated.")

    # Event Snapshots
    st.header("Event Snapshots")
    st.caption(
        "Expand each event to view its snapshot and adjust the band-exit / recovery "
        "intersection points if needed. Click **Recalculate Compliance** below when done."
    )
    if snapshot_paths or not df_events.empty:
        overrides = st.session_state.setdefault("intersection_overrides", {})

        for snap_i, (idx, row) in enumerate(df_events.iterrows()):
            ev_ts     = row["Timestamp"]
            dkw       = row.get("dKw", 0)
            direction = "▲" if dkw > 0 else "▼"

            ov = overrides.get(idx, {})
            has_override = (
                ov.get("v_exit_offset", 0.0) != 0.0 or ov.get("v_rec_override") is not None
                or ov.get("f_exit_offset", 0.0) != 0.0 or ov.get("f_rec_override") is not None
            )
            badge = "🔧 " if has_override else ""
            _rated = st.session_state.get("rated_load_kw")
            _pct_str = (
                f"  ({dkw / _rated * 100:+.1f}% rated)"
                if _rated and _rated > 0 else ""
            )
            label = (
                f"{badge}Event {snap_i + 1} — {ev_ts.strftime('%H:%M:%S')}  "
                f"|  {direction} {abs(dkw):.0f} kW{_pct_str}"
            )

            with st.expander(label, expanded=(snap_i == 0)):
                # Snapshot image (if generated)
                if snap_i < len(snapshot_paths) and os.path.exists(snapshot_paths[snap_i]):
                    st.image(snapshot_paths[snap_i], use_container_width=True)
                else:
                    st.info("No snapshot image for this event.")

                st.divider()
                st.markdown("**Adjust Intersection Points**")
                _render_event_intersection_controls(idx, row, overrides)

        _render_intersection_footer(overrides)
    else:
        st.info("No event snapshots generated.")

    # Download all analysis assets as ZIP
    st.divider()
    assets_zip = io.BytesIO()
    with zipfile.ZipFile(assets_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for folder in [GRAPH_DIR, SNAPSHOT_DIR, IMAGE_DIR]:
            if os.path.exists(folder):
                for root, _, files_list in os.walk(folder):
                    for file in files_list:
                        full_path = os.path.join(root, file)
                        arcname = os.path.relpath(full_path, OUTPUT_BASE)
                        zipf.write(full_path, arcname=arcname)
    assets_zip.seek(0)
    st.download_button(
        label="⬇️ Download All Analysis Assets as ZIP",
        data=assets_zip.getvalue(),
        file_name="PQA_Analysis_Results.zip",
        mime="application/zip",
    )


# ============================================================
# REPORT GENERATION — top-level so it always runs on button click
# ============================================================
if generate_clicked and (selected_template_path is not None or html_template_str is not None):
    client_name_display = st.session_state.get("client_name", client_name)
    _success = False

    with st.sidebar:
        with st.status("Generating report...", expanded=True) as _status:
            try:
                st.write("⚙️ Building content map...")
                config_values = {
                    "report_title": report_title,
                    "gen_sn": gen_sn,
                    "site_address": site_address,
                    "custom_text": custom_text,
                }
                p_map = get_placeholder_map(
                    client_name_display, config_values,
                    df=st.session_state.get("df_raw"),
                    graph_dir=GRAPH_DIR, snapshot_dir=SNAPSHOT_DIR, image_dir=IMAGE_DIR,
                )
                log.info(f"Placeholder map built: {list(p_map.keys())}")

                output_base = os.path.join(OUTPUT_BASE, report_filename)
                entry = {"name": report_filename, "files": {}}

                if report_format == "Word Template":
                    log.info(f"Word report — template: {selected_template_path}, output: {report_filename}")
                    st.write("📝 Injecting content into Word template...")
                    docx_path = generate_docx(selected_template_path, p_map, output_name=output_base)
                    log.info(f"DOCX generated: {docx_path}")

                    st.write("💾 Word document ready — reading file...")
                    with open(docx_path, "rb") as f:
                        entry["files"]["docx"] = f.read()

                    st.write("🖨️ Converting to PDF (timeout: 45s)...")
                    pdf_path = f"{output_base}.pdf"
                    pdf_ok, pdf_log = convert_to_pdf(docx_path, pdf_path)
                    log.info(f"PDF conversion {'succeeded' if pdf_ok else 'failed'}:\n{pdf_log}")
                    with st.expander("PDF converter log", expanded=not pdf_ok):
                        st.code(pdf_log, language="text")
                    if pdf_ok:
                        with open(pdf_path, "rb") as f:
                            entry["files"]["pdf"] = f.read()
                        st.write("✅ PDF ready.")
                    else:
                        st.warning(
                            "**PDF conversion failed** — only the Word (.docx) file is available.\n\n"
                            "**Converters tried:** LibreOffice → WeasyPrint → fpdf2\n\n"
                            "**To fix on macOS:** `brew install --cask libreoffice` then restart the app.\n\n"
                            "See the **PDF converter log** expander above for per-converter error details."
                        )

                else:  # HTML Template
                    log.info(f"HTML report — output: {report_filename}")
                    st.write("📝 Injecting content into HTML template...")
                    html_result = generate_html_report(p_map, html_template_str, output_name=output_base)

                    with open(html_result["html"], "rb") as f:
                        entry["files"]["html"] = f.read()
                    st.write("💾 HTML ready.")

                    pdf_log = html_result.get("pdf_log", "")
                    with st.expander("PDF converter log", expanded="pdf" not in html_result):
                        st.code(pdf_log, language="text")

                    if "pdf" in html_result:
                        with open(html_result["pdf"], "rb") as f:
                            entry["files"]["pdf"] = f.read()
                        st.write("✅ PDF ready.")
                    else:
                        st.warning(
                            "**PDF conversion failed** — only the HTML file is available.\n\n"
                            "**Converters tried:** WeasyPrint → LibreOffice → reportlab\n\n"
                            "**To fix on macOS:** `brew install --cask libreoffice` then restart the app,\n"
                            "or `brew install cairo pango` for WeasyPrint.\n\n"
                            "See the **PDF converter log** expander above for details."
                        )

                reports = st.session_state.get("generated_reports", [])
                reports.append(entry)
                st.session_state["generated_reports"] = reports

                _status.update(label=f"✅ '{report_filename}' generated!", state="complete", expanded=False)
                log.info(f"Report '{report_filename}' added to session state.")
                _success = True

            except Exception as _exc:
                log.exception(f"Report generation failed: {_exc}")
                _status.update(label=f"❌ Failed: {_exc}", state="error", expanded=True)
                st.write(str(_exc))

    if _success:
        st.rerun()


# ============================================================
# DEV MODE SAVE — persist settings to JSON after every full render
# ============================================================
if _ds.get("dev_mode"):
    # Collect values from already-keyed widgets via session_state
    for _k in ("fri_upper", "fri_lower", "frd_upper", "frd_lower",
                "rated_load_input", "nom_v_preset", "nom_v_custom", "report_format"):
        _ds[_k] = st.session_state.get(_k, _DEV_DEFAULTS.get(_k))
    _ds["_tf_csv_path"] = st.session_state.get("_tf_csv_path", "")
    _ds["tf_start_text"] = st.session_state.get(_TF_START_TEXT, "")
    _ds["tf_end_text"]   = st.session_state.get(_TF_END_TEXT, "")
    _save_dev_settings(_ds)


# ============================================================
# DEBUG LOG PANEL — always visible at bottom of sidebar
# ============================================================
with st.sidebar:
    st.divider()
    with st.expander("🐛 Debug Log", expanded=False):
        col_dbg1, col_dbg2 = st.columns(2)
        if col_dbg1.button("Refresh", key="dbg_refresh", use_container_width=True):
            pass  # triggers a rerun which re-reads the file
        if col_dbg2.button("Clear", key="dbg_clear", use_container_width=True):
            open(LOG_FILE, "w").close()
            st.rerun()
        try:
            with open(LOG_FILE, "r") as _lf:
                _lines = _lf.readlines()
            # Show last 60 lines
            _recent = "".join(_lines[-60:]) if len(_lines) > 60 else "".join(_lines)
            st.code(_recent or "(empty)", language="text")
        except FileNotFoundError:
            st.caption("No log file yet.")
