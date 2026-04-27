"""
Power Quality Analysis - Streamlit Application

Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import os
import shutil
import zipfile
import base64
import io
import glob
import datetime
import logging
import json
from pathlib import Path

from analysis import AnalysisConfig, load_and_prepare_csv, load_winscope_xls, perform_analysis, check_compliance, calculate_recovery_time
from visualizations import (
    generate_plots,
    generate_all_snapshots,
    generate_temp_pressure_plots,
    plot_load_change_snapshot,
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

def _get_build_version():
    """Get build version from git: 0.{feature_count}.{total_commits}"""
    try:
        import subprocess
        # Count total commits
        total_commits = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=_APP_DIR,
            capture_output=True,
            text=True,
            timeout=5
        ).stdout.strip()
        # Count feature commits (feat: prefix)
        feature_commits = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=_APP_DIR,
            capture_output=True,
            text=True,
            timeout=5
        ).stdout
        feature_count = len([line for line in feature_commits.split('\n') if ' feat:' in line])
        return f"0.{feature_count}.{total_commits}"
    except Exception:
        return "0.0.0"

# --- Output directories ---
OUTPUT_BASE = os.path.join(_APP_DIR, "output")
GRAPH_DIR = os.path.join(OUTPUT_BASE, "Graphs")
SNAPSHOT_DIR = os.path.join(OUTPUT_BASE, "Snapshots")
IMAGE_DIR = os.path.join(OUTPUT_BASE, "Images")
TEMPLATE_DIR = os.path.join(OUTPUT_BASE, "Template")

# --- Persistent upload directories ---
UPLOADS_CSV_DIR = os.path.join(_APP_DIR, "uploads", "csv")
UPLOADS_TEMPLATE_DIR = os.path.join(_APP_DIR, "uploads", "templates")
UPLOADS_WINSCOPE_DIR = os.path.join(_APP_DIR, "uploads", "winscope")
os.makedirs(UPLOADS_CSV_DIR, exist_ok=True)
os.makedirs(UPLOADS_TEMPLATE_DIR, exist_ok=True)
os.makedirs(UPLOADS_WINSCOPE_DIR, exist_ok=True)

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
    "show_intersections": False,
    "show_debug": False,
    "detection_window": 5.0,
    "recovery_verify_s": 6.0,
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
    "expected_steps_input": "",
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


def _show_progress_popup(placeholder, pct: int, step: str, title: str = "Processing"):
    """Render a fixed-position progress popup into a st.empty() placeholder."""
    placeholder.markdown(f"""
<div class="pqa-popup-backdrop"></div>
<div class="pqa-popup-card">
    <div class="pqa-popup-title">{title}</div>
    <div class="pqa-popup-step">{step}</div>
    <div class="pqa-popup-track">
        <div class="pqa-popup-fill" style="width:{pct}%"></div>
    </div>
    <div class="pqa-popup-pct">{pct}%</div>
</div>
""", unsafe_allow_html=True)


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

        with st.spinner("Recalculating compliance…"):
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
                v_max_dev=cfg.voltage_max_deviation_pct,
                f_max_dev=cfg.frequency_max_deviation_pct,
                show_debug=st.session_state.get("show_debug", False),
                show_intersections=st.session_state.get("show_intersections", False),
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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ── Global ── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
.main .block-container {
    padding-top: 1.5rem;
    padding-bottom: 2.5rem;
    max-width: 1240px;
}

/* ── Sidebar ── */
div[data-testid="stSidebar"] {
    background-color: #0a1628;
    border-right: 1px solid #1a2744;
}
div[data-testid="stSidebar"] * {
    color: #cbd5e1 !important;
}
div[data-testid="stSidebar"] h1 {
    font-size: 0.95rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
    color: #f1f5f9 !important;
}
div[data-testid="stSidebar"] h2,
div[data-testid="stSidebar"] h3 {
    font-size: 0.65rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    color: #475569 !important;
    margin-top: 0.15rem !important;
    margin-bottom: 0.5rem !important;
}
div[data-testid="stSidebar"] label,
div[data-testid="stSidebar"] .stCheckbox label {
    font-size: 0.795rem !important;
    color: #94a3b8 !important;
}
div[data-testid="stSidebar"] hr {
    border-color: #1a2744 !important;
    margin: 0.85rem 0 !important;
}
div[data-testid="stSidebar"] input,
div[data-testid="stSidebar"] .stNumberInput input,
div[data-testid="stSidebar"] .stTextInput input {
    background-color: #111e35 !important;
    border: 1px solid #263352 !important;
    color: #e2e8f0 !important;
    border-radius: 6px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.78rem !important;
    transition: border-color 0.15s ease !important;
}
div[data-testid="stSidebar"] input:focus,
div[data-testid="stSidebar"] .stNumberInput input:focus,
div[data-testid="stSidebar"] .stTextInput input:focus {
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 2px rgba(59,130,246,0.15) !important;
}
div[data-testid="stSidebar"] .stSelectbox > div > div {
    background-color: #111e35 !important;
    border: 1px solid #263352 !important;
    color: #e2e8f0 !important;
    border-radius: 6px !important;
}
/* Sidebar scrollbar */
div[data-testid="stSidebar"]::-webkit-scrollbar { width: 4px; }
div[data-testid="stSidebar"]::-webkit-scrollbar-track { background: transparent; }
div[data-testid="stSidebar"]::-webkit-scrollbar-thumb { background: #263352; border-radius: 4px; }

/* ── Run Analysis button — prominent CTA ── */
/* Streamlit 1.35+ uses data-testid="baseButton-primary/secondary" — kind attr removed */
div[data-testid="stSidebar"] button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 100%) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    font-size: 0.88rem !important;
    letter-spacing: 0.03em !important;
    box-shadow: 0 2px 8px rgba(37,99,235,0.35) !important;
    transition: all 0.18s ease !important;
    padding: 0.6rem 1rem !important;
}
div[data-testid="stSidebar"] button[data-testid="baseButton-primary"]:hover {
    background: linear-gradient(135deg, #1e40af 0%, #1d4ed8 100%) !important;
    box-shadow: 0 4px 16px rgba(37,99,235,0.5) !important;
    transform: translateY(-1px) !important;
}
div[data-testid="stSidebar"] button[data-testid="baseButton-primary"]:active {
    transform: translateY(0) !important;
    box-shadow: 0 1px 4px rgba(37,99,235,0.3) !important;
}
/* Primary buttons in main area */
button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 100%) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 7px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    letter-spacing: 0.02em !important;
    box-shadow: 0 2px 6px rgba(37,99,235,0.25) !important;
    transition: all 0.18s ease !important;
}
button[data-testid="baseButton-primary"]:hover {
    background: linear-gradient(135deg, #1e40af 0%, #1d4ed8 100%) !important;
    box-shadow: 0 4px 14px rgba(37,99,235,0.4) !important;
    transform: translateY(-1px) !important;
}
/* All secondary sidebar buttons — base style */
div[data-testid="stSidebar"] button[data-testid="baseButton-secondary"] {
    background-color: #111e35 !important;
    color: #64748b !important;
    border: 1px solid #1e2f4d !important;
    border-radius: 5px !important;
    font-size: 0.74rem !important;
    transition: all 0.15s ease !important;
}
div[data-testid="stSidebar"] button[data-testid="baseButton-secondary"]:hover {
    color: #94a3b8 !important;
    border-color: #334155 !important;
}

/* ── Sidebar inline reset icon buttons ─────────────────────────────────────
   Layout: st.columns([7, 1]) — text_input in wide col, ↺ button in narrow col.
   .pqa-rst-btn is an invisible marker div placed inside the narrow column so
   we can target that column's stVerticalBlock via :has().
   Making the stVerticalBlock flex + justify-content:flex-end pushes the button
   to the bottom of the column, aligning it with the input box (not the label).
   ──────────────────────────────────────────────────────────────────────── */

/* Hide the marker — it's only a CSS hook, not visible content */
.pqa-rst-btn { display: none !important; }

/* Push the reset button to the bottom of its column (aligns with input box) */
div[data-testid="stSidebar"]
div[data-testid="stVerticalBlock"]:has(.pqa-rst-btn) {
    display: flex !important;
    flex-direction: column !important;
    justify-content: flex-end !important;
    padding-bottom: 0.55rem !important;
}

/* Collapse the stButton wrapper so no extra padding inflates the height */
div[data-testid="stSidebar"]
div[data-testid="stVerticalBlock"]:has(.pqa-rst-btn)
[data-testid="stButton"] {
    padding: 0 !important;
    margin: 0 !important;
}

/* Style the reset button as a small square */
div[data-testid="stSidebar"]
div[data-testid="stVerticalBlock"]:has(.pqa-rst-btn)
button[data-testid="baseButton-secondary"] {
    background: transparent !important;
    color: #64748b !important;
    border: 1.5px solid #64748b !important;
    border-radius: 6px !important;
    width: 2rem !important;
    height: 2rem !important;
    min-height: 0 !important;
    min-width: 0 !important;
    padding: 0 !important;
    font-size: 0.85rem !important;
    line-height: 1 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-shadow: none !important;
    cursor: pointer !important;
    transition: color 0.15s, border-color 0.15s, background 0.15s !important;
}
div[data-testid="stSidebar"]
div[data-testid="stVerticalBlock"]:has(.pqa-rst-btn)
button[data-testid="baseButton-secondary"]:hover {
    color: #94a3b8 !important;
    border-color: #94a3b8 !important;
    background: rgba(148, 163, 184, 0.08) !important;
}

/* ── Download buttons ── */
div[data-testid="stSidebar"] .stDownloadButton > button {
    background-color: #0f1f3a !important;
    color: #60a5fa !important;
    border: 1px solid #1e3a5f !important;
    border-radius: 6px !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    transition: all 0.15s ease !important;
}
div[data-testid="stSidebar"] .stDownloadButton > button:hover {
    background-color: #1a3460 !important;
    border-color: #3b82f6 !important;
    color: #93c5fd !important;
}

/* ── Main area headings ── */
.main h1 {
    font-size: 1.8rem;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.03em;
    line-height: 1.2;
    margin-bottom: 0.25rem;
}
.main h2 {
    font-size: 1.05rem;
    font-weight: 700;
    color: #0f172a;
    letter-spacing: -0.01em;
    margin-top: 2rem;
    margin-bottom: 0.5rem;
    padding-left: 0.75rem;
    border-left: 3px solid #2563eb;
}
.main h3 {
    font-size: 0.95rem;
    font-weight: 600;
    color: #1e293b;
    margin-top: 1rem;
    margin-bottom: 0.4rem;
}

/* ── Metric cards ── */
div[data-testid="stMetric"] {
    background: linear-gradient(145deg, #0c1a30 0%, #111e35 100%);
    border: 1px solid #1e3050;
    border-radius: 10px;
    padding: 1rem 1.25rem !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.03);
    transition: box-shadow 0.2s ease;
}
div[data-testid="stMetric"]:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.3);
}
div[data-testid="stMetric"] label {
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: #475569 !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 1.7rem !important;
    font-weight: 700 !important;
    color: #e2e8f0 !important;
}

/* ── Expanders ── */
.stExpander {
    border: 1px solid #e8ecf2 !important;
    border-radius: 10px !important;
    overflow: hidden !important;
    transition: box-shadow 0.15s ease !important;
    margin-bottom: 0.5rem !important;
}
.stExpander:hover {
    box-shadow: 0 2px 12px rgba(0,0,0,0.06) !important;
}
.stExpander summary {
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    color: #1e293b !important;
    padding: 0.75rem 1rem !important;
    transition: background 0.15s ease !important;
}
.stExpander summary:hover {
    background: #f8fafc !important;
}
.stExpander[open] summary {
    border-bottom: 1px solid #e8ecf2 !important;
    background: #f8fafc !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0 !important;
    border-bottom: 2px solid #e2e8f0 !important;
    background: transparent !important;
    padding: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    color: #64748b !important;
    padding: 0.6rem 1.1rem !important;
    border-radius: 0 !important;
    border: none !important;
    background: transparent !important;
    letter-spacing: 0.01em !important;
    transition: color 0.15s ease !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #1e293b !important;
    background: #f8fafc !important;
}
.stTabs [aria-selected="true"] {
    color: #2563eb !important;
    border-bottom: 2px solid #2563eb !important;
    margin-bottom: -2px !important;
    background: transparent !important;
}

/* ── Dataframe ── */
.stDataFrame {
    border: 1px solid #e2e8f0 !important;
    border-radius: 10px !important;
    overflow: hidden !important;
}

/* ── Alert / info boxes ── */
.stAlert {
    border-radius: 8px !important;
    font-size: 0.865rem !important;
    border-left-width: 4px !important;
}

/* ── Status / spinner ── */
.stStatus {
    border-radius: 10px !important;
    font-size: 0.85rem !important;
    border: 1px solid #e2e8f0 !important;
}

/* ── Progress popup overlay ── */
.pqa-popup-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.52);
    backdrop-filter: blur(3px);
    -webkit-backdrop-filter: blur(3px);
    z-index: 9998;
}
.pqa-popup-card {
    position: fixed;
    top: 50%;
    left: calc(50vw + 10.5rem);
    transform: translate(-50%, -50%);
    z-index: 9999;
    background: #ffffff;
    border-radius: 16px;
    padding: 2rem 2.5rem 1.75rem;
    box-shadow: 0 24px 80px rgba(15, 23, 42, 0.22), 0 2px 8px rgba(15, 23, 42, 0.08);
    min-width: 360px;
    max-width: 460px;
    width: 90vw;
}
.pqa-popup-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: #0f172a;
    margin: 0 0 0.3rem;
    letter-spacing: -0.01em;
}
.pqa-popup-step {
    font-size: 0.78rem;
    color: #64748b;
    margin: 0 0 1.1rem;
    min-height: 1.1em;
}
.pqa-popup-track {
    height: 6px;
    background: #e2e8f0;
    border-radius: 99px;
    overflow: hidden;
}
.pqa-popup-fill {
    height: 100%;
    border-radius: 99px;
    background: linear-gradient(90deg, #2563eb 0%, #3b82f6 100%);
    box-shadow: 0 0 8px rgba(37, 99, 235, 0.35);
    transition: width 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}
.pqa-popup-pct {
    font-size: 0.7rem;
    color: #94a3b8;
    text-align: right;
    margin-top: 0.4rem;
}

/* ── Divider ── */
hr {
    border-color: #f1f5f9 !important;
    margin: 1.25rem 0 !important;
}

/* ── Caption / small text ── */
.stCaption, small {
    color: #64748b !important;
    font-size: 0.75rem !important;
}

/* ── Code blocks in debug log ── */
.stCodeBlock, .stCode code {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.72rem !important;
}

/* ── Download button in main area ── */
.stDownloadButton > button {
    border-radius: 7px !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    transition: all 0.15s ease !important;
}

/* ── Spinner text ── */
.stSpinner > div { color: #2563eb !important; }

/* ── Toast ── */
.stToast {
    border-radius: 8px !important;
    font-size: 0.85rem !important;
}

/* ── PQA custom metric strip ── */
.pqa-metrics {
    display: flex; gap: 12px; margin: 1.25rem 0;
}
.pqa-metric-card {
    flex: 1; background: linear-gradient(145deg, #0c1a30, #111e35);
    border: 1px solid #1e3050; border-radius: 10px;
    padding: 1rem 1.25rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    transition: box-shadow 0.2s ease;
}
.pqa-metric-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.3); }
.pqa-metric-card.pass  { border-color: #166534; box-shadow: 0 2px 8px rgba(22,101,52,0.2); }
.pqa-metric-card.fail  { border-color: #991b1b; box-shadow: 0 2px 8px rgba(153,27,27,0.2); }
.pqa-metric-card.overall-pass { border-color: #16a34a; border-width: 2px; }
.pqa-metric-card.overall-fail { border-color: #dc2626; border-width: 2px; }
.pqa-metric-label {
    font-size: 0.65rem; font-weight: 700; letter-spacing: 0.12em;
    text-transform: uppercase; color: #475569; margin-bottom: 0.4rem;
}
.pqa-metric-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.7rem; font-weight: 700; color: #e2e8f0; line-height: 1;
}
.pqa-metric-card.pass  .pqa-metric-value { color: #4ade80; }
.pqa-metric-card.fail  .pqa-metric-value { color: #f87171; }
.pqa-metric-sub {
    font-size: 0.72rem; color: #64748b; margin-top: 0.25rem;
}
.pqa-overall-badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 0.15rem 0.65rem; border-radius: 20px;
    font-size: 0.75rem; font-weight: 700; letter-spacing: 0.05em;
    margin-top: 0.4rem;
}
.pqa-overall-badge.pass { background: rgba(22,163,74,0.15); color: #4ade80; }
.pqa-overall-badge.fail { background: rgba(220,38,38,0.15); color: #f87171; }

/* ── Section title with accent bar ── */
.pqa-section-header {
    display: flex; align-items: center; gap: 10px;
    margin: 2rem 0 0.75rem;
}
.pqa-section-bar {
    width: 4px; height: 22px; border-radius: 2px; background: #2563eb; flex-shrink: 0;
}
.pqa-section-title {
    font-size: 1.05rem; font-weight: 700; color: #0f172a; letter-spacing: -0.01em;
}
.pqa-section-badge {
    font-size: 0.7rem; font-weight: 600; padding: 0.15rem 0.55rem;
    border-radius: 20px; background: #eff6ff; color: #2563eb;
    letter-spacing: 0.02em;
}
.pqa-section-badge.green { background: #f0fdf4; color: #16a34a; }
.pqa-section-badge.red   { background: #fef2f2; color: #dc2626; }
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


def _get_ws_time_range(path):
    """Read a WinScope XLS path and return (start_str, end_str) or (None, None)."""
    try:
        temp_df = load_winscope_xls(path)
        if not temp_df.empty:
            return (
                temp_df["Timestamp"].min().strftime("%H:%M:%S"),
                temp_df["Timestamp"].max().strftime("%H:%M:%S"),
            )
    except Exception:
        pass
    return (None, None)


# nom_v and nom_f are set by the sidebar Display Options section below.

def _render_compliance_html(df):
    cols = list(df.columns)
    header = "".join(f"<th>{c}</th>" for c in cols)
    rows_html = []
    for _, row in df.iterrows():
        cells = []
        is_fail = str(row.get("Compliance Status", "")).strip() == "Fail"
        row_bg = "rgba(254,242,242,0.6)" if is_fail else "#ffffff"
        row_bg_hover = "#fef2f2" if is_fail else "#f8fafc"
        for c, v in zip(cols, row):
            v = "" if str(v) in ("nan", "None") else str(v)
            if c == "Compliance Status":
                if v == "Pass":
                    badge = (
                        '<span style="display:inline-flex;align-items:center;gap:4px;'
                        'background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;'
                        'border-radius:20px;padding:2px 10px;font-size:12px;font-weight:700;'
                        'letter-spacing:0.03em;">&#10003; Pass</span>'
                    )
                else:
                    badge = (
                        '<span style="display:inline-flex;align-items:center;gap:4px;'
                        'background:#fef2f2;color:#dc2626;border:1px solid #fecaca;'
                        'border-radius:20px;padding:2px 10px;font-size:12px;font-weight:700;'
                        'letter-spacing:0.03em;">&#10007; Fail</span>'
                    )
                cells.append(f'<td style="background:{row_bg};white-space:nowrap;">{badge}</td>')
            elif c == "Event Time":
                cells.append(f'<td style="background:{row_bg};font-family:\'JetBrains Mono\',monospace;font-size:12px;white-space:nowrap;">{v}</td>')
            else:
                cells.append(f'<td style="background:{row_bg};">{v}</td>')
        rows_html.append(
            f'<tr onmouseenter="this.querySelectorAll(\'td\').forEach(t=>t.style.background=\'{row_bg_hover}\')" '
            f'onmouseleave="this.querySelectorAll(\'td\').forEach(t=>t.style.background=\'{row_bg}\')">'
            f"{''.join(cells)}</tr>"
        )
    table_rows = "\n".join(rows_html)
    return f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
      .pqa-table {{
        width: 100%; border-collapse: separate; border-spacing: 0;
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 13.5px; color: #111827;
        border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden;
      }}
      .pqa-table th {{
        background: #f8fafc; font-weight: 700; color: #374151;
        padding: 10px 14px; text-align: left;
        border-bottom: 2px solid #e2e8f0;
        font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase;
        white-space: nowrap;
      }}
      .pqa-table th:not(:last-child) {{ border-right: 1px solid #e5e7eb; }}
      .pqa-table td {{
        padding: 10px 14px;
        border-bottom: 1px solid #f1f5f9;
        border-right: 1px solid #f1f5f9;
        vertical-align: top; line-height: 1.55;
        transition: background 0.1s ease;
      }}
      .pqa-table td:last-child {{ border-right: none; }}
      .pqa-table tr:last-child td {{ border-bottom: none; }}
      .pqa-table td small {{ color: #6b7280; font-size: 11.5px; display:block; }}
    </style>
    <div style="border-radius:10px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
    <table class="pqa-table">
      <thead><tr>{header}</tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
    </div>
    """



# ── Cold-start: load persisted settings into session state ────────────────────
if "_ds" not in st.session_state:
    _loaded = _load_dev_settings()
    st.session_state["_ds"] = _loaded
    # Pre-populate keyed widgets that have NO value= parameter (safe — no conflict).
    # Widgets with key= + value= are handled by passing value=_ds.get(...) instead.
    for _k in ("fri_upper", "fri_lower", "frd_upper", "frd_lower",
                "nom_v_preset", "nom_v_custom", "rated_load_input",
                "expected_steps_input", "report_format", "detection_window"):
        if _k not in st.session_state:
            st.session_state[_k] = _loaded.get(_k, _DEV_DEFAULTS[_k])
    # Time filter: restore only if the saved CSV path still matches
    if _loaded.get("_tf_csv_path"):
        st.session_state["_tf_csv_path"] = _loaded["_tf_csv_path"]
        st.session_state[_TF_START_TEXT] = _loaded.get("tf_start_text", "")
        st.session_state[_TF_END_TEXT]   = _loaded.get("tf_end_text", "")
_ds: dict = st.session_state["_ds"]  # shorthand used throughout the sidebar
# ─────────────────────────────────────────────────────────────────────────────

# ── Active tab mode (drives sidebar content) ──────────────────────────────────
if "_active_tab" not in st.session_state:
    st.session_state["_active_tab"] = "compliance"

# Defaults — overridden in the sidebar block based on active mode.
selected_csv_path = None
client_name = ""
auto_start = ""
auto_end = ""
start_time = ""
end_time = ""
run_clicked = False
_selected_ws_path = None
_ws_client_name = ""
_ws_run = False
generate_clicked = False
ws_generate_clicked = False

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:8px;padding:0.75rem 0 0.25rem;">
      <div style="width:28px;height:28px;background:rgba(37,99,235,0.18);border-radius:7px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
        <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49M7.76 7.76a6 6 0 0 0 0 8.49"/></svg>
      </div>
      <span style="font-size:0.78rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#94a3b8;">Configuration</span>
    </div>
    """, unsafe_allow_html=True)

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

    # ── Mode Selector ──────────────────────────────────────────
    _active_tab = st.session_state.get("_active_tab", "compliance")
    _compliance_mode = (_active_tab == "compliance")
    _mc1, _mc2 = st.columns(2)
    if _mc1.button("⚡ Compliance", use_container_width=True,
                   type="primary" if _compliance_mode else "secondary",
                   key="sidebar_mode_compliance"):
        st.session_state["_active_tab"] = "compliance"
        st.rerun()
    if _mc2.button("📊 WinScope", use_container_width=True,
                   type="primary" if not _compliance_mode else "secondary",
                   key="sidebar_mode_winscope"):
        st.session_state["_active_tab"] = "winscope"
        st.rerun()

    st.divider()

    if _compliance_mode:
        # ── 1. CSV Upload ──────────────────────────────────────────
        st.subheader("Data Files")

        # Track previous CSV count to detect single vs multiple uploads
        if "_prev_csv_count" not in st.session_state:
            st.session_state["_prev_csv_count"] = len(glob.glob(os.path.join(UPLOADS_CSV_DIR, "*.csv")))

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
                # Auto-select if only 1 file was uploaded, otherwise leave blank
                if len(_saved) == 1:
                    _ds["selected_csv_name"] = _saved[0]
                else:
                    _ds["selected_csv_name"] = ""
            if _failed:
                st.error(f"Failed to save: {', '.join(_failed)} — check Debug Log")

        saved_csvs = sorted(glob.glob(os.path.join(UPLOADS_CSV_DIR, "*.csv")))
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

        if all_csv_names:
            _saved_csv = _ds.get("selected_csv_name", "")
            # If selector was cleared (empty string), keep it at blank (None index) so user must choose
            if _saved_csv == "":
                _csv_idx = None
            elif _saved_csv in all_csv_names:
                _csv_idx = all_csv_names.index(_saved_csv)
            else:
                _csv_idx = None
            selected_name = st.selectbox("Select CSV to analyse", all_csv_names, index=_csv_idx)
            _ds["selected_csv_name"] = selected_name
            selected_csv_path = os.path.join(UPLOADS_CSV_DIR, selected_name)
            client_name = os.path.splitext(selected_name)[0]
            auto_start, auto_end = _get_csv_time_range(selected_csv_path)

    else:
        # ── 1. WinScope Files ──────────────────────────────────────
        st.subheader("WinScope Data")
        _ws_uploaded = st.file_uploader("Upload WinScope .xls file", type=["xls"], key="ws_file_uploader")
        if _ws_uploaded is not None:
            _ws_save_path = os.path.join(UPLOADS_WINSCOPE_DIR, _ws_uploaded.name)
            with open(_ws_save_path, "wb") as _wsf:
                _wsf.write(_ws_uploaded.getbuffer())

        _saved_ws = sorted(glob.glob(os.path.join(UPLOADS_WINSCOPE_DIR, "*.xls")))
        for _wp in list(_saved_ws):
            _wn = os.path.basename(_wp)
            _ws_kb = os.path.getsize(_wp) / 1024
            _wc1, _wc2 = st.columns([5, 1])
            _wc1.markdown(f"📋 **{_wn}**  \n<small>{_ws_kb:.0f} KB</small>", unsafe_allow_html=True)
            if _wc2.button("✕", key=f"rm_ws_{_wn}", help=f"Remove {_wn}"):
                os.remove(_wp)
                st.rerun()
        _saved_ws = sorted(glob.glob(os.path.join(UPLOADS_WINSCOPE_DIR, "*.xls")))
        _ws_names = [os.path.basename(p) for p in _saved_ws]
        if _ws_names:
            _ws_sel_name = st.selectbox("Select WinScope file", _ws_names, key="ws_selector")
            _selected_ws_path = os.path.join(UPLOADS_WINSCOPE_DIR, _ws_sel_name)
            _ws_client_name = os.path.splitext(_ws_sel_name)[0]
            _ws_tr_key = f"_ws_tr_{_selected_ws_path}"
            if _ws_tr_key not in st.session_state:
                st.session_state[_ws_tr_key] = _get_ws_time_range(_selected_ws_path)
            auto_start, auto_end = st.session_state[_ws_tr_key]

    st.divider()

    # ── 2. Acceptance Criteria ────────────────────────────────
    st.subheader("Acceptance Criteria")
    apply_iso = st.checkbox("Apply ISO 8528 Presets", value=_ds.get("apply_iso", False))
    show_limits = st.checkbox("Show Limits on Graphs", value=_ds.get("show_limits", False))
    show_limits_snapshots = st.checkbox("Show Limits on Snapshots", value=_ds.get("show_limits_snapshots", False))
    show_intersections = st.checkbox(
        "Show Intersection Points",
        value=_ds.get("show_intersections", False),
        help="Overlay the exact band-exit (orange ★) and recovery (lime ★) crossing markers on event snapshots, "
             "along with the compliance band limits used for each event. "
             "Useful for verifying that calculated recovery times match the waveform.",
    )
    if _ds.get("dev_mode", False):
        show_debug = st.checkbox("Show Event Detection (De-bugging)", value=_ds.get("show_debug", False))
    else:
        show_debug = False
    _dw_col, _dw_rst = st.columns([7, 1])
    with _dw_col:
        detection_window = st.number_input(
            "Detection Window (s)",
            key="detection_window",
            min_value=1.0, max_value=30.0, step=1.0,
            help="Time window used to group consecutive load step rows into a single event.",
        )
    with _dw_rst:
        st.markdown('<div class="pqa-rst-btn"></div>', unsafe_allow_html=True)
        if st.button("↺", key="reset_detection_window"):
            st.session_state["detection_window"] = 5.0
            st.rerun()
    snapshot_window = st.number_input(
        "Snapshot Window (s)",
        value=float(_ds.get("snapshot_window", 10.0)),
        min_value=3.0, max_value=60.0, step=1.0,
        help="Seconds shown either side of each event in snapshots. Also sets the window used to find peak voltage/frequency deviation.",
    )
    recovery_verify_s = 6.0
    if dev_mode:
        recovery_verify_s = st.number_input(
            "Recovery Verify Window (s)",
            value=float(_ds.get("recovery_verify_s", 6.0)),
            min_value=1.0, max_value=30.0, step=1.0,
            help="After a recovery candidate is found, verify the signal stays in-band for this many seconds. Handles oscillating waveforms.",
        )
    _ds["apply_iso"] = apply_iso
    _ds["show_limits"] = show_limits
    _ds["show_limits_snapshots"] = show_limits_snapshots
    _ds["show_intersections"] = show_intersections
    _ds["show_debug"] = show_debug
    _ds["detection_window"] = detection_window
    _ds["snapshot_window"] = snapshot_window
    _ds["recovery_verify_s"] = recovery_verify_s

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
    _rl_col, _rl_rst = st.columns([7, 1])
    with _rl_col:
        rated_load_str = st.text_input(
            "Rated Load (kW)",
            help="Optional. When set, load change % is calculated against this value.",
            key="rated_load_input",
        )
    with _rl_rst:
        st.markdown('<div class="pqa-rst-btn"></div>', unsafe_allow_html=True)
        if st.button("↺", key="reset_rated_load"):
            st.session_state["rated_load_input"] = ""
            st.rerun()
    st.session_state["rated_load_str"] = rated_load_str
    try:
        rated_load_kw = float(rated_load_str) if rated_load_str.strip() else None
    except ValueError:
        st.warning("Rated Load must be a number.")
        rated_load_kw = None
    st.session_state["rated_load_kw"] = rated_load_kw

    _es_col, _es_rst = st.columns([7, 1])
    with _es_col:
        expected_steps_str = st.text_input(
            "No. Expected Load Steps",
            help="Optional. If set, an error is shown when detected events don't match this count.",
            key="expected_steps_input",
        )
    with _es_rst:
        st.markdown('<div class="pqa-rst-btn"></div>', unsafe_allow_html=True)
        if st.button("↺", key="reset_expected_steps"):
            st.session_state["expected_steps_input"] = ""
            st.rerun()
    try:
        expected_steps = int(expected_steps_str) if expected_steps_str.strip() else None
    except ValueError:
        st.warning("Expected Load Steps must be a whole number.")
        expected_steps = None
    st.session_state["expected_steps"] = expected_steps

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
    if _compliance_mode:
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
    else:
        ln_to_ll_mode = "force_ll"

    st.divider()

    # ── 5. Time Filter ────────────────────────────────────────
    _tf_active_path = selected_csv_path if _compliance_mode else _selected_ws_path
    if selected_csv_path is not None or _selected_ws_path is not None:
        st.subheader("Time Filter")

        if st.session_state.get("_tf_csv_path") != _tf_active_path:
            st.session_state["_tf_csv_path"] = _tf_active_path
            st.session_state[_TF_START_TEXT] = auto_start or ""
            st.session_state[_TF_END_TEXT]   = auto_end or ""

        _s_col, _s_rst = st.columns([7, 1])
        with _s_col:
            start_time_text = st.text_input(
                "Start Time", key=_TF_START_TEXT, placeholder="HH:MM:SS",
                help="Filter analysis to start from this time.",
            )
        with _s_rst:
            st.markdown('<div class="pqa-rst-btn"></div>', unsafe_allow_html=True)
            if st.button("\u21ba", key="reset_start_time"):
                st.session_state[_TF_START_TEXT] = auto_start or ""
                st.rerun()

        _e_col, _e_rst = st.columns([7, 1])
        with _e_col:
            end_time_text = st.text_input(
                "End Time", key=_TF_END_TEXT, placeholder="HH:MM:SS",
                help="Filter analysis to end at this time.",
            )
        with _e_rst:
            st.markdown('<div class="pqa-rst-btn"></div>', unsafe_allow_html=True)
            if st.button("\u21ba", key="reset_end_time"):
                st.session_state[_TF_END_TEXT] = auto_end or ""
                st.rerun()

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


    # ── Run Analysis / WinScope Analysis ─────────────────────
    if _compliance_mode:
        if selected_csv_path is not None:
            run_clicked = st.button("\u26a1 Run Analysis", type="primary", use_container_width=True)
        else:
            st.info("Upload CSV files above to begin.")
    else:
        if _selected_ws_path is not None:
            _ws_run = st.button("\u26a1 Run WinScope Analysis", type="primary", use_container_width=True, key="ws_run_btn")
        else:
            st.info("Upload a WinScope .xls file above to begin.")

    st.divider()

    # ── 6. Report Details ─────────────────────────────────────
    st.subheader("Report Details")
    if "report_title" not in st.session_state:
        st.session_state["report_title"] = client_name
    report_title = st.text_input("Report Title", key="report_title", placeholder="Enter report/client name")
    pqa_serial = st.text_input("PQA Serial No.", value=_ds.get("pqa_serial", ""), placeholder="Enter PQA serial number")
    gen_sn = st.text_input("Generator Serial Number", value=_ds.get("gen_sn", ""), placeholder="Enter Gen S/N")
    site_address = st.text_input("Site Address", value=_ds.get("site_address", ""), placeholder="Enter site address")
    custom_text = st.text_input("Custom Text Field", value=_ds.get("custom_text", ""), placeholder="Enter custom info")
    _ds["pqa_serial"] = pqa_serial
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
            _saved_tpl, _failed_tpl = [], []
            for f in new_templates:
                dest = os.path.join(UPLOADS_TEMPLATE_DIR, f.name)
                try:
                    f.seek(0)
                    with open(dest, "wb") as out:
                        out.write(f.read())
                    _saved_tpl.append(f.name)
                    log.info(f"Template saved: {dest}")
                except Exception as e:
                    _failed_tpl.append(f.name)
                    log.error(f"Failed to save template {f.name}: {e}")
                    st.error(f"Failed to save {f.name} — check Debug Log")
            # Auto-select if only 1 template was uploaded, otherwise leave blank
            if _saved_tpl:
                if len(_saved_tpl) == 1:
                    st.session_state["_selected_template"] = _saved_tpl[0]
                else:
                    st.session_state["_selected_template"] = ""

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
            # Check if we have a stored selection, otherwise keep blank
            _stored_tpl = st.session_state.get("_selected_template", "")
            if _stored_tpl == "":
                _tpl_idx = None
            elif _stored_tpl in all_template_names:
                _tpl_idx = all_template_names.index(_stored_tpl)
            else:
                _tpl_idx = None
            selected_template_name = st.selectbox("Select Template", all_template_names, index=_tpl_idx)
            selected_template_path = os.path.join(UPLOADS_TEMPLATE_DIR, selected_template_name) if selected_template_name else None

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

    if "report_filename" not in st.session_state:
        st.session_state["report_filename"] = client_name or "PQA_Report"
    report_filename = st.text_input(
        "Report Filename",
        key="report_filename",
        placeholder="Enter filename (no extension)",
    )

    if report_format == "Word Template":
        download_format = st.selectbox(
            "Download Format",
            ["PDF", "Word (.docx)", "Word+PDF"],
            key="download_format_word",
        )
    else:
        download_format = st.selectbox(
            "Download Format",
            ["PDF", "HTML", "HTML+PDF"],
            key="download_format_html",
        )

    # ── Not-recovered warning ──────────────────────────────────
    _df_ev_check = (
        st.session_state.get("df_events") if _compliance_mode
        else st.session_state.get("ws_df_events")
    )
    _has_nr = False
    if _df_ev_check is not None and not _df_ev_check.empty:
        _has_nr = bool(
            _df_ev_check.get("V_not_recovered", False).any()
            or _df_ev_check.get("F_not_recovered", False).any()
        )

    if _has_nr:
        st.warning(
            "⚠️ One or more events have voltage or frequency that did not recover "
            "from the previous step. The report will include these flags unless removed."
        )
        remove_nr_warnings = st.checkbox(
            "Remove warnings from report", key="remove_nr_warnings"
        )
    else:
        remove_nr_warnings = False
        st.session_state.pop("remove_nr_warnings", None)

    _btn_disabled = _has_nr and not remove_nr_warnings

    analysis_ready = (
        st.session_state.get("analysis_done") if _compliance_mode
        else st.session_state.get("ws_analysis_done")
    )
    if report_format == "Word Template":
        if selected_template_path is not None and analysis_ready:
            _gen_btn = st.button("\U0001f4c4 Generate Report", type="primary",
                                 use_container_width=True, disabled=_btn_disabled)
            if _compliance_mode:
                generate_clicked = _gen_btn
            else:
                ws_generate_clicked = _gen_btn
        elif not analysis_ready:
            st.caption("Run analysis first to enable report generation.")
        else:
            st.caption("Upload a template above to generate a report.")
    else:  # HTML Template
        if analysis_ready:
            _gen_btn = st.button("\U0001f4c4 Generate Report", type="primary",
                                 use_container_width=True, disabled=_btn_disabled)
            if _compliance_mode:
                generate_clicked = _gen_btn
            else:
                ws_generate_clicked = _gen_btn
        else:
            st.caption("Run analysis first to enable report generation.")

    # ── Generated Reports List (sidebar) ──────────────────────
    sidebar_reports = st.session_state.get("generated_reports", [])
    if sidebar_reports:
        st.divider()
        st.subheader("Generated Reports")
        for i, entry in enumerate(sidebar_reports):
            st.markdown(f"**{entry['name']}**")
            c1, c2, c3 = st.columns([5, 5, 2])
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
            if c3.button("🗑", key=f"sb_del_{i}", help="Remove this report", use_container_width=True):
                st.session_state["generated_reports"].pop(i)
                st.rerun()

        if st.button("⬇️ Download All Reports", use_container_width=True, key="dl_all_reports"):
            parts = []
            for entry in sidebar_reports:
                for fmt, mime in [
                    ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                    ("pdf", "application/pdf"),
                    ("html", "text/html"),
                ]:
                    if fmt in entry["files"]:
                        b64 = base64.b64encode(bytes(entry["files"][fmt])).decode()
                        fname = f"{entry['name']}.{fmt}"
                        parts.append(f'{{name:"{fname}",data:"{b64}",mime:"{mime}"}}')
            files_js = "[" + ",".join(parts) + "]"
            st.session_state["_dl_all_html"] = (
                f"<script>var _f={files_js};"
                "_f.forEach(function(f,i){setTimeout(function(){"
                'var a=document.createElement("a");'
                'a.href="data:"+f.mime+";base64,"+f.data;'
                "a.download=f.name;document.body.appendChild(a);a.click();document.body.removeChild(a);"
                "},i*500);});</script>"
            )

        if st.session_state.get("_dl_all_html"):
            st.components.v1.html(st.session_state["_dl_all_html"], height=0)
            st.session_state["_dl_all_html"] = None


# ============================================================
# MAIN AREA
# ============================================================
_dev_mode = st.session_state.get("_ds", {}).get("dev_mode", False)
_build_version = _get_build_version() if _dev_mode else ""
_version_badge = f' <span style="font-size:1.3rem;color:#64748b;font-weight:500;margin-left:0.5rem;">build {_build_version}</span>' if _build_version else ""

st.markdown(f"""
<div style="display:flex;align-items:flex-start;gap:14px;margin-bottom:1.5rem;padding-bottom:1.25rem;border-bottom:2px solid #e2e8f0;">
  <div style="width:42px;height:42px;background:linear-gradient(135deg,#1d4ed8,#2563eb);border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 2px 8px rgba(37,99,235,0.35);">
    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polyline></svg>
  </div>
  <div>
    <h1 style="margin:0;padding:0;border:none;font-size:1.65rem;font-weight:800;color:#0f172a;letter-spacing:-0.03em;line-height:1.15;">Power Quality Analysis{_version_badge}</h1>
    <p style="margin:0.2rem 0 0;font-size:0.8rem;color:#64748b;font-weight:400;">ISO 8528 compliance · Load event detection · Recovery time analysis</p>
  </div>
</div>
""", unsafe_allow_html=True)

_active_tab_main = st.session_state.get("_active_tab", "compliance")
_TAB_LABELS = ["⚡ Compliance Analysis", "📊 WinScope Viewer", "🔧 Set Point Comparison"]
_TAB_KEYS   = ["compliance", "winscope", "setpoint"]
_chosen_tab = st.radio(
    "", _TAB_LABELS,
    index=_TAB_KEYS.index(_active_tab_main) if _active_tab_main in _TAB_KEYS else 0,
    horizontal=True, label_visibility="collapsed", key="main_tab_selector",
)
_active_tab_main = _TAB_KEYS[_TAB_LABELS.index(_chosen_tab)]
if _active_tab_main != st.session_state.get("_active_tab", "compliance"):
    st.session_state["_active_tab"] = _active_tab_main
    st.rerun()

if _active_tab_main == "compliance":
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
                recovery_verify_s=recovery_verify_s,
            )

            _prog = st.empty()
            try:
                log.info(f"Run Analysis clicked — CSV: {selected_csv_path}, time: {start_time}–{end_time}")
                _show_progress_popup(_prog, 10, "Loading CSV data…", "Running Analysis")
                df_raw = load_and_prepare_csv(selected_csv_path, start_time=start_time, end_time=end_time)
                if df_raw.empty:
                    _prog.empty()
                    log.warning("CSV loaded but no rows after time filter.")
                    st.error("No data found. Check your CSV and time range.")
                    st.stop()
                log.info(f"CSV loaded: {len(df_raw)} rows")
                _show_progress_popup(_prog, 25, "Running power quality analysis…", "Running Analysis")
                df_proc, df_events = perform_analysis(df_raw, config)
                log.info(f"Analysis done: {len(df_events)} events detected")
            except Exception:
                _prog.empty()
                log.exception("perform_analysis failed")
                st.error("Analysis failed — see Debug Log in the sidebar for details.")
                st.stop()

            _show_progress_popup(_prog, 40, "Building results summary…", "Running Analysis")
            st.session_state.update({
                "df_raw": df_raw,
                "df_proc": df_proc,
                "df_events": df_events,
                "client_name": client_name,
                "config": config,
                "analysis_done": True,
                "generated_reports": st.session_state.get("generated_reports", []),
                "intersection_overrides": {},   # clear any overrides from previous run
                "event_window_overrides": {},   # clear per-event snapshot window overrides
                "show_debug": show_debug,
                "show_intersections": show_intersections,
                "show_limits_snapshots": show_limits_snapshots,
            })

            _n_pass = int((df_events["Compliance_Status"] == "Pass").sum()) if not df_events.empty and "Compliance_Status" in df_events.columns else 0
            _n_fail = int((df_events["Compliance_Status"] == "Fail").sum()) if not df_events.empty and "Compliance_Status" in df_events.columns else 0
            _n_events = len(df_events)
            _overall_cls = "overall-pass" if _n_fail == 0 and _n_events > 0 else ("overall-fail" if _n_fail > 0 else "")
            _overall_label = "ALL PASS" if _n_fail == 0 and _n_events > 0 else (f"{_n_fail} FAIL{'S' if _n_fail > 1 else ''}" if _n_fail > 0 else "—")
            _overall_badge_cls = "pass" if _n_fail == 0 and _n_events > 0 else "fail"
            st.markdown(f"""
            <div class="pqa-metrics">
              <div class="pqa-metric-card">
                <div class="pqa-metric-label">Data Points</div>
                <div class="pqa-metric-value">{len(df_proc):,}</div>
                <div class="pqa-metric-sub">rows processed</div>
              </div>
              <div class="pqa-metric-card">
                <div class="pqa-metric-label">Events Detected</div>
                <div class="pqa-metric-value">{_n_events}</div>
                <div class="pqa-metric-sub">load steps found</div>
              </div>
              <div class="pqa-metric-card pass">
                <div class="pqa-metric-label">Passed</div>
                <div class="pqa-metric-value">{_n_pass}</div>
                <div class="pqa-metric-sub">of {_n_events} events</div>
              </div>
              <div class="pqa-metric-card {'fail' if _n_fail > 0 else ''}">
                <div class="pqa-metric-label">Failed</div>
                <div class="pqa-metric-value">{_n_fail}</div>
                <div class="pqa-metric-sub">compliance issues</div>
              </div>
              <div class="pqa-metric-card {_overall_cls}" style="flex:0.7;">
                <div class="pqa-metric-label">Result</div>
                <div class="pqa-overall-badge {_overall_badge_cls}" style="margin-top:0.6rem;font-size:0.85rem;">{_overall_label}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # Main time-series graphs are always clean — debug overlays live on snapshots only.
            plot_kwargs = dict(
                output_dir=GRAPH_DIR, show_limits=show_limits,
                nom_v=nom_v, nom_f=nom_f, tol_v=v_tol, tol_f=f_tol,
                v_max_dev=v_max_dev, f_max_dev=f_max_dev,
                show_debug=False,
                df_events=None,
                thresh_kw=load_thresh,
            )
            try:
                _show_progress_popup(_prog, 55, "Generating voltage plot…", "Running Analysis")
                graph_paths = generate_plots(df_proc, client_name, metric_keys=["Avg_Voltage_LL"], **plot_kwargs)
                st.session_state["graph_paths"] = graph_paths
                log.info("Voltage plot generated")

                _show_progress_popup(_prog, 68, "Generating remaining plots…", "Running Analysis")
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
                    _show_progress_popup(_prog, 80, "Generating compliance table…", "Running Analysis")
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
                    _show_progress_popup(_prog, 90, "Generating event snapshots…", "Running Analysis")
                    snapshot_paths = generate_all_snapshots(
                        df_raw, df_events, client_name, output_dir=SNAPSHOT_DIR,
                        show_limits=show_limits_snapshots,
                        nom_v=nom_v, nom_f=nom_f, tol_v=v_tol, tol_f=f_tol,
                        v_max_dev=v_max_dev, f_max_dev=f_max_dev,
                        show_debug=show_debug,
                        show_intersections=show_intersections,
                        rated_load_kw=rated_load_kw,
                        window_s=snapshot_window,
                    )
                    log.info(f"{len(snapshot_paths)} snapshots generated")
                except Exception:
                    log.exception("Snapshot generation failed")
            else:
                st.warning("No load events detected above the threshold.")

            _show_progress_popup(_prog, 100, "Done!", "Running Analysis")
            _prog.empty()
            st.session_state["snapshot_paths"] = snapshot_paths
            st.session_state["table_path"] = table_path
            st.success(f"Analysis complete — **{len(df_events)} events** detected · **{len(graph_paths)} plots** · **{len(snapshot_paths)} snapshots**")

    else:
        st.markdown("""
        <div style="text-align:center;padding:3.5rem 2rem;background:#f8fafc;border-radius:12px;border:2px dashed #e2e8f0;margin-top:1rem;">
          <div style="width:52px;height:52px;background:#eff6ff;border-radius:14px;display:flex;align-items:center;justify-content:center;margin:0 auto 1rem;">
            <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polyline></svg>
          </div>
          <p style="font-size:1rem;font-weight:600;color:#0f172a;margin:0 0 0.4rem;">No data loaded</p>
          <p style="font-size:0.85rem;color:#64748b;margin:0;">Upload a CSV file in the sidebar to begin analysis.</p>
        </div>
        """, unsafe_allow_html=True)


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
            _n_pass_r = int((df_events["Compliance_Status"] == "Pass").sum()) if "Compliance_Status" in df_events.columns else 0
            _n_fail_r = int((df_events["Compliance_Status"] == "Fail").sum()) if "Compliance_Status" in df_events.columns else 0
            _badge_cls = "green" if _n_fail_r == 0 else "red"
            _badge_txt = f"All {_n_pass_r} passed" if _n_fail_r == 0 else f"{_n_fail_r} failed"
            st.markdown(f"""
            <div class="pqa-section-header">
              <div class="pqa-section-bar"></div>
              <span class="pqa-section-title">Compliance Results</span>
              <span class="pqa-section-badge {_badge_cls}">{_badge_txt}</span>
            </div>""", unsafe_allow_html=True)

            # Expected load steps check
            _expected = st.session_state.get("expected_steps")
            _detected = len(df_events)
            if _expected is not None and _detected != _expected:
                st.error(
                    f"Expected {_expected} load step{'s' if _expected != 1 else ''} "
                    f"but detected {_detected}. "
                    "Adjust the Detection Window or review the CSV data."
                )

            # Missing recovery time warnings — flag events where the signal left
            # the band but no recovery was recorded (data ended before recovery,
            # or recovery could not be determined).
            _v_no_rec = []
            _f_no_rec = []
            for _ei, (_eidx, _erow) in enumerate(df_events.iterrows()):
                _ev_label = f"Event {_ei + 1} ({_erow['Timestamp'].strftime('%H:%M:%S')})"
                if pd.notnull(_erow.get("V_exit_ts")) and pd.isna(_erow.get("V_rec_s")):
                    _v_no_rec.append(_ev_label)
                if pd.notnull(_erow.get("F_exit_ts")) and pd.isna(_erow.get("F_rec_s")):
                    _f_no_rec.append(_ev_label)
            if _v_no_rec:
                st.error(
                    "**Voltage recovery not detected** for: "
                    + ", ".join(_v_no_rec)
                    + ". The voltage left the tolerance band but did not recover within "
                    "the recorded data. Check the CSV length or review the snapshot."
                )
            if _f_no_rec:
                st.error(
                    "**Frequency recovery not detected** for: "
                    + ", ".join(_f_no_rec)
                    + ". The frequency left the tolerance band but did not recover within "
                    "the recorded data. Check the CSV length or review the snapshot."
                )

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

            # Voltage Deviation — actual measured min/max voltage (V)
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

            # Frequency Deviation — actual measured min/max frequency (Hz)
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


            # Height: header (~50px) + per row (~80px base for 2-line cells) +
            # extra for any rows with failure reasons (up to 3 wrapped lines).
            _row_heights = []
            for _, _r in disp.iterrows():
                _fr = str(_r.get("Failure Reasons", ""))
                _extra_lines = _fr.count("<br>") if _fr not in ("", "nan") else 0
                _row_heights.append(80 + _extra_lines * 20)
            table_height = 60 + sum(_row_heights)
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
        st.markdown("""
        <div class="pqa-section-header">
          <div class="pqa-section-bar" style="background:#0891b2;"></div>
          <span class="pqa-section-title">Time-Series Plots</span>
        </div>""", unsafe_allow_html=True)
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
        st.markdown("""
        <div class="pqa-section-header">
          <div class="pqa-section-bar" style="background:#9333ea;"></div>
          <span class="pqa-section-title">Event Snapshots</span>
        </div>""", unsafe_allow_html=True)
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
                v_nr = bool(row.get("V_not_recovered", False))
                f_nr = bool(row.get("F_not_recovered", False))
                nr_badge = "⚠️ " if (v_nr or f_nr) else ""
                label = (
                    f"{nr_badge}{badge}Event {snap_i + 1} — {ev_ts.strftime('%H:%M:%S')}  "
                    f"|  {direction} {abs(dkw):.0f} kW{_pct_str}"
                )

                with st.expander(label, expanded=(snap_i == 0)):
                    # Not-recovered warning
                    if v_nr and f_nr:
                        st.error("Voltage and Frequency did not recover from the previous step.")
                    elif v_nr:
                        st.error("Voltage did not recover from the previous step.")
                    elif f_nr:
                        st.error("Frequency did not recover from the previous step.")

                    # Dev Mode — per-event snapshot window override
                    if dev_mode:
                        _win_overrides = st.session_state.setdefault("event_window_overrides", {})
                        _cur_win = float(_win_overrides.get(idx, config.snapshot_window_s))
                        _col_w, _col_btn = st.columns([3, 1])
                        with _col_w:
                            _new_win = st.number_input(
                                "Snapshot window (s)",
                                min_value=3.0, max_value=120.0, step=1.0,
                                value=_cur_win,
                                key=f"snap_window_{idx}",
                                help="Seconds shown either side of this event. Click Regenerate to apply.",
                            )
                        with _col_btn:
                            st.write("")
                            _regen = st.button("↺ Regenerate", key=f"regen_snap_{idx}", use_container_width=True)
                        if _regen:
                            _win_overrides[idx] = _new_win
                            _new_path = plot_load_change_snapshot(
                                st.session_state["df_raw"],
                                event_ts=row["Timestamp"],
                                load_change=row["dKw"],
                                load_before=row["Avg_kW"] - row["dKw"],
                                load_after=row["Avg_kW"],
                                client_name=client_name_display,
                                output_dir=SNAPSHOT_DIR,
                                show_limits=st.session_state.get("show_limits_snapshots", False),
                                nom_v=config.nominal_voltage,
                                nom_f=config.nominal_frequency,
                                tol_v=config.voltage_tolerance_pct,
                                tol_f=config.frequency_tolerance_pct,
                                show_debug=st.session_state.get("show_debug", False),
                                show_intersections=st.session_state.get("show_intersections", False),
                                event_row=row,
                                rated_load_kw=st.session_state.get("rated_load_kw"),
                                window_s=_new_win,
                            )
                            _paths = list(st.session_state.get("snapshot_paths", []))
                            if snap_i < len(_paths):
                                _paths[snap_i] = _new_path
                            else:
                                _paths.append(_new_path)
                            st.session_state["snapshot_paths"] = _paths
                            st.rerun()

                    # Snapshot image (if generated)
                    _snap_path = snapshot_paths[snap_i] if snap_i < len(snapshot_paths) else None
                    if _snap_path and os.path.exists(_snap_path):
                        st.image(_snap_path, use_container_width=True)
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
        _rpt_prog = st.empty()
        _pdf_log_data: dict = {}   # collect logs/warnings to render after popup clears

        try:
            _show_progress_popup(_rpt_prog, 10, "Building content map…", "Generating Report")
            config_values = {
                "report_title": report_title,
                "pqa_serial": pqa_serial,
                "gen_sn": gen_sn,
                "site_address": site_address,
                "custom_text": custom_text,
            }

            # If removing not-recovered warnings, regenerate snapshots without flags
            _snap_dir = SNAPSHOT_DIR
            if st.session_state.get("remove_nr_warnings") and _has_nr:
                _cfg = st.session_state.get("config")
                _snap_dir_clean = os.path.join(OUTPUT_BASE, "Snapshots_clean")
                os.makedirs(_snap_dir_clean, exist_ok=True)
                _df_ev_clean = df_events.copy()
                _df_ev_clean["V_not_recovered"] = False
                _df_ev_clean["F_not_recovered"] = False
                _show_progress_popup(_rpt_prog, 20, "Regenerating clean snapshots…", "Generating Report")
                generate_all_snapshots(
                    st.session_state["df_raw"], _df_ev_clean, client_name_display,
                    output_dir=_snap_dir_clean,
                    show_limits=st.session_state.get("show_limits_snapshots", False),
                    nom_v=_cfg.nominal_voltage if _cfg else 415.0,
                    nom_f=_cfg.nominal_frequency if _cfg else 50.0,
                    tol_v=_cfg.voltage_tolerance_pct if _cfg else 1.0,
                    tol_f=_cfg.frequency_tolerance_pct if _cfg else 0.5,
                    v_max_dev=_cfg.voltage_max_deviation_pct if _cfg else 15.0,
                    f_max_dev=_cfg.frequency_max_deviation_pct if _cfg else 7.0,
                    show_debug=False,
                    rated_load_kw=st.session_state.get("rated_load_kw"),
                    window_s=_cfg.snapshot_window_s if _cfg else 10.0,
                )
                _snap_dir = _snap_dir_clean

            _show_progress_popup(_rpt_prog, 35, "Mapping placeholders…", "Generating Report")
            p_map = get_placeholder_map(
                client_name_display, config_values,
                df=st.session_state.get("df_raw"),
                graph_dir=GRAPH_DIR, snapshot_dir=_snap_dir, image_dir=IMAGE_DIR,
            )
            log.info(f"Placeholder map built: {list(p_map.keys())}")

            _n_events_rpt = len(st.session_state.get("df_events", pd.DataFrame()))
            _n_snaps_mapped = sum(1 for k in p_map if k.startswith("{{Snapshot_"))
            if _n_snaps_mapped < _n_events_rpt:
                _pdf_log_data["snap_warning"] = (
                    f"Template has placeholders for {_n_snaps_mapped} snapshot(s) "
                    f"but {_n_events_rpt} events were detected. "
                    f"Add `{{{{Snapshot_{_n_snaps_mapped + 1}}}}}` … "
                    f"`{{{{Snapshot_{_n_events_rpt}}}}}` to your template to include all snapshots."
                )

            output_base = os.path.join(OUTPUT_BASE, report_filename)
            entry = {"name": report_filename, "files": {}}

            if report_format == "Word Template":
                log.info(f"Word report — template: {selected_template_path}, output: {report_filename}, format: {download_format}")
                _show_progress_popup(_rpt_prog, 50, "Injecting content into Word template…", "Generating Report")
                docx_path = generate_docx(selected_template_path, p_map, output_name=output_base)
                log.info(f"DOCX generated: {docx_path}")

                if download_format in ("Word (.docx)", "Word+PDF"):
                    with open(docx_path, "rb") as f:
                        entry["files"]["docx"] = f.read()

                if download_format in ("PDF", "Word+PDF"):
                    _show_progress_popup(_rpt_prog, 75, "Converting to PDF…", "Generating Report")
                    pdf_path = f"{output_base}.pdf"
                    pdf_ok, pdf_log = convert_to_pdf(docx_path, pdf_path)
                    log.info(f"PDF conversion {'succeeded' if pdf_ok else 'failed'}:\n{pdf_log}")
                    _pdf_log_data["word_pdf_log"] = pdf_log
                    _pdf_log_data["word_pdf_ok"] = pdf_ok
                    if pdf_ok:
                        with open(pdf_path, "rb") as f:
                            entry["files"]["pdf"] = f.read()
                    else:
                        _pdf_log_data["word_pdf_warn"] = (
                            "**PDF conversion failed.**\n\n"
                            "**Converters tried:** LibreOffice → docx2pdf → WeasyPrint → fpdf2\n\n"
                            "**To fix on macOS:** `brew install --cask libreoffice` then restart the app.\n\n"
                            "See the **PDF converter log** expander above for per-converter error details."
                        )

            else:  # HTML Template
                log.info(f"HTML report — output: {report_filename}, format: {download_format}")
                _show_progress_popup(_rpt_prog, 50, "Injecting content into HTML template…", "Generating Report")
                html_result = generate_html_report(p_map, html_template_str, output_name=output_base)

                if download_format in ("HTML", "HTML+PDF"):
                    with open(html_result["html"], "rb") as f:
                        entry["files"]["html"] = f.read()

                if download_format in ("PDF", "HTML+PDF"):
                    _show_progress_popup(_rpt_prog, 75, "Converting to PDF…", "Generating Report")
                    pdf_log = html_result.get("pdf_log", "")
                    _pdf_log_data["html_pdf_log"] = pdf_log
                    _pdf_log_data["html_pdf_ok"] = "pdf" in html_result
                    if "pdf" in html_result:
                        with open(html_result["pdf"], "rb") as f:
                            entry["files"]["pdf"] = f.read()
                    else:
                        _pdf_log_data["html_pdf_warn"] = (
                            "**PDF conversion failed.**\n\n"
                            "**Converters tried:** WeasyPrint → LibreOffice → reportlab\n\n"
                            "**To fix on macOS:** `brew install --cask libreoffice` then restart the app,\n"
                            "or `brew install cairo pango` for WeasyPrint.\n\n"
                            "See the **PDF converter log** expander above for details."
                        )

            reports = st.session_state.get("generated_reports", [])
            reports.append(entry)
            st.session_state["generated_reports"] = reports

            _show_progress_popup(_rpt_prog, 100, "Done!", "Generating Report")
            _rpt_prog.empty()
            log.info(f"Report '{report_filename}' added to session state.")
            _success = True

        except Exception as _exc:
            _rpt_prog.empty()
            log.exception(f"Report generation failed: {_exc}")
            st.error(f"Report generation failed: {_exc}")

        # Render any deferred logs / warnings now that the popup is gone
        if _pdf_log_data.get("snap_warning"):
            st.warning(_pdf_log_data["snap_warning"])
        if "word_pdf_log" in _pdf_log_data:
            with st.expander("PDF converter log", expanded=not _pdf_log_data.get("word_pdf_ok")):
                st.code(_pdf_log_data["word_pdf_log"], language="text")
            if not _pdf_log_data.get("word_pdf_ok") and "word_pdf_warn" in _pdf_log_data:
                st.warning(_pdf_log_data["word_pdf_warn"])
        if "html_pdf_log" in _pdf_log_data:
            with st.expander("PDF converter log", expanded=not _pdf_log_data.get("html_pdf_ok")):
                st.code(_pdf_log_data["html_pdf_log"], language="text")
            if not _pdf_log_data.get("html_pdf_ok") and "html_pdf_warn" in _pdf_log_data:
                st.warning(_pdf_log_data["html_pdf_warn"])

        if _success:
            st.rerun()




elif _active_tab_main == "winscope":
    st.markdown("""
    <div style="display:flex;align-items:flex-start;gap:14px;margin-bottom:1.5rem;padding-bottom:1.25rem;border-bottom:2px solid #e2e8f0;">
      <div style="width:42px;height:42px;background:linear-gradient(135deg,#0e7490,#0891b2);border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 2px 8px rgba(8,145,178,0.35);">
        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
      </div>
      <div>
        <h1 style="margin:0;padding:0;border:none;font-size:1.65rem;font-weight:800;color:#0f172a;letter-spacing:-0.03em;line-height:1.15;">WinScope Viewer</h1>
        <p style="margin:0.2rem 0 0;font-size:0.8rem;color:#64748b;font-weight:400;">High-resolution WinScope .xls data · No interpolation · Full compliance analysis</p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if _selected_ws_path is not None:
        with st.expander("Preview WinScope data", expanded=False):
            try:
                _ws_prev = load_winscope_xls(_selected_ws_path)
                st.dataframe(_ws_prev.head(10), width="stretch")
            except Exception as _we:
                st.error(f"Preview failed: {_we}")
        st.caption(f"Using acceptance criteria from sidebar configuration · Source: **{_ws_client_name}**")


        if _ws_run:
            _ws_graph_dir = os.path.join(OUTPUT_BASE, "ws_Graphs")
            _ws_snap_dir  = os.path.join(OUTPUT_BASE, "ws_Snapshots")
            _ws_img_dir   = os.path.join(OUTPUT_BASE, "ws_Images")
            import shutil as _shutil
            for _d in [_ws_graph_dir, _ws_snap_dir, _ws_img_dir]:
                if os.path.exists(_d):
                    _shutil.rmtree(_d, ignore_errors=True)
                os.makedirs(_d, exist_ok=True)

            _ws_prog = st.empty()
            try:
                log.info(f"WinScope analysis started — file: {_selected_ws_path}")
                _show_progress_popup(_ws_prog, 5,  "Loading WinScope file…",    "WinScope Analysis")
                _ws_df_raw = load_winscope_xls(_selected_ws_path)
                if start_time and end_time and not _ws_df_raw.empty:
                    try:
                        _ws_date = _ws_df_raw["Timestamp"].dt.date.iloc[0]
                        _ws_start_dt = pd.to_datetime(f"{_ws_date} {start_time}")
                        _ws_end_dt   = pd.to_datetime(f"{_ws_date} {end_time}")
                        _ws_df_raw = _ws_df_raw[
                            (_ws_df_raw["Timestamp"] >= _ws_start_dt) &
                            (_ws_df_raw["Timestamp"] <= _ws_end_dt)
                        ].reset_index(drop=True)
                        log.info(f"WinScope time filter applied: {start_time}–{end_time}, {len(_ws_df_raw)} rows remaining")
                    except Exception as _tfe:
                        log.warning(f"WinScope time filter failed: {_tfe}")

                _show_progress_popup(_ws_prog, 20, "Running event detection…",  "WinScope Analysis")
                _ws_config = AnalysisConfig(
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
                    ln_to_ll_mode="force_ll",
                    recovery_verify_s=recovery_verify_s,
                    skip_interpolation=True,
                )
                _ws_df_proc, _ws_df_events = perform_analysis(_ws_df_raw, _ws_config)

                _show_progress_popup(_ws_prog, 45, "Generating voltage plot…",  "WinScope Analysis")
                _ws_plot_kw = dict(
                    output_dir=_ws_graph_dir, show_limits=show_limits,
                    nom_v=nom_v, nom_f=nom_f, tol_v=v_tol, tol_f=f_tol,
                    v_max_dev=v_max_dev, f_max_dev=f_max_dev,
                    show_debug=False, df_events=None, thresh_kw=load_thresh,
                )
                _ws_graph_paths = generate_plots(_ws_df_proc, _ws_client_name,
                                                 metric_keys=["Avg_Voltage_LL"], **_ws_plot_kw)
                _show_progress_popup(_ws_prog, 58, "Generating remaining plots…", "WinScope Analysis")
                _ws_other = generate_plots(_ws_df_proc, _ws_client_name,
                                           metric_keys=["Avg_kW", "Avg_Current", "Avg_Frequency", "Avg_PF", "Avg_THD_F"],
                                           **_ws_plot_kw)
                _ws_graph_paths.update(_ws_other)

                _show_progress_popup(_ws_prog, 65, "Generating temp/pressure plots…", "WinScope Analysis")
                try:
                    _ws_tp_paths = generate_temp_pressure_plots(
                        _ws_df_raw, _ws_client_name, output_dir=_ws_graph_dir,
                    )
                except Exception:
                    log.exception("Temp/pressure plot generation failed")
                    _ws_tp_paths = {}

                if not _ws_df_events.empty:
                    _show_progress_popup(_ws_prog, 72, "Generating compliance table…", "WinScope Analysis")
                    _ws_table_file = os.path.join(_ws_img_dir, f"{_ws_client_name}_table.png")
                    try:
                        _ws_table_path = save_compliance_table_as_image(
                            _ws_df_events, _ws_table_file, _ws_client_name,
                            nom_v=nom_v, nom_f=nom_f,
                        )
                    except Exception:
                        log.exception("WinScope compliance table generation failed")
                        _ws_table_path = None

                    _show_progress_popup(_ws_prog, 88, "Generating event snapshots…", "WinScope Analysis")
                    try:
                        _ws_snapshot_paths = generate_all_snapshots(
                            _ws_df_raw, _ws_df_events, _ws_client_name,
                            output_dir=_ws_snap_dir,
                            show_limits=show_limits_snapshots,
                            nom_v=nom_v, nom_f=nom_f, tol_v=v_tol, tol_f=f_tol,
                            v_max_dev=v_max_dev, f_max_dev=f_max_dev,
                            show_debug=show_debug,
                            show_intersections=show_intersections,
                            window_s=snapshot_window,
                        )
                    except Exception:
                        log.exception("WinScope snapshot generation failed")
                        _ws_snapshot_paths = []
                else:
                    _ws_table_path = None
                    _ws_snapshot_paths = []
                    st.warning("No load events detected above the threshold.")

                st.session_state["ws_analysis_done"]   = True
                st.session_state["ws_df_raw"]           = _ws_df_raw
                st.session_state["ws_df_proc"]          = _ws_df_proc
                st.session_state["ws_df_events"]        = _ws_df_events
                st.session_state["ws_graph_paths"]      = _ws_graph_paths
                st.session_state["ws_tp_paths"]         = _ws_tp_paths
                st.session_state["ws_snapshot_paths"]   = _ws_snapshot_paths
                st.session_state["ws_table_path"]       = _ws_table_path
                st.session_state["ws_client_name"]      = _ws_client_name
                st.session_state["ws_config"]           = _ws_config
                st.session_state["ws_graph_dir"]        = _ws_graph_dir
                st.session_state["ws_snap_dir"]         = _ws_snap_dir
                st.session_state["ws_img_dir"]          = _ws_img_dir
                _show_progress_popup(_ws_prog, 100, "Complete!", "WinScope Analysis")
                log.info("WinScope analysis complete")
            except Exception as _wex:
                log.exception("WinScope analysis failed")
                st.error(f"WinScope analysis failed: {_wex}")
            finally:
                _ws_prog.empty()

    # ── WinScope Results ──────────────────────────────────────────────────────
    if st.session_state.get("ws_analysis_done"):
        _ws_ev  = st.session_state["ws_df_events"]
        _ws_gp  = st.session_state.get("ws_graph_paths", {})
        _ws_sp  = st.session_state.get("ws_snapshot_paths", [])
        _ws_tp  = st.session_state.get("ws_table_path")
        _ws_cfg = st.session_state["ws_config"]
        _ws_cn  = st.session_state["ws_client_name"]

        if not _ws_ev.empty:
            _ws_total   = len(_ws_ev)
            _ws_n_pass  = int((_ws_ev["Compliance_Status"] == "Pass").sum()) if "Compliance_Status" in _ws_ev.columns else 0
            _ws_n_fail  = _ws_total - _ws_n_pass
            _ws_oc      = "overall-pass" if _ws_n_fail == 0 and _ws_total > 0 else ("overall-fail" if _ws_n_fail > 0 else "")
            _ws_bc      = "green"        if _ws_n_fail == 0 else "red"
            _ws_bt      = f"All {_ws_n_pass} passed" if _ws_n_fail == 0 else f"{_ws_n_fail} failed"
            _ws_overall_label = "ALL PASS" if _ws_n_fail == 0 and _ws_total > 0 else (f"{_ws_n_fail} FAIL{'S' if _ws_n_fail > 1 else ''}" if _ws_n_fail > 0 else "—")
            _ws_overall_badge = "pass" if _ws_n_fail == 0 and _ws_total > 0 else "fail"
            st.markdown(f"""
            <div class="pqa-metrics">
              <div class="pqa-metric-card">
                <div class="pqa-metric-label">Data Points</div>
                <div class="pqa-metric-value">{len(st.session_state.get("ws_df_proc", pd.DataFrame())):,}</div>
                <div class="pqa-metric-sub">rows processed</div>
              </div>
              <div class="pqa-metric-card">
                <div class="pqa-metric-label">Events Detected</div>
                <div class="pqa-metric-value">{_ws_total}</div>
                <div class="pqa-metric-sub">load steps found</div>
              </div>
              <div class="pqa-metric-card pass">
                <div class="pqa-metric-label">Passed</div>
                <div class="pqa-metric-value">{_ws_n_pass}</div>
                <div class="pqa-metric-sub">of {_ws_total} events</div>
              </div>
              <div class="pqa-metric-card {'fail' if _ws_n_fail > 0 else ''}">
                <div class="pqa-metric-label">Failed</div>
                <div class="pqa-metric-value">{_ws_n_fail}</div>
                <div class="pqa-metric-sub">compliance issues</div>
              </div>
              <div class="pqa-metric-card {_ws_oc}" style="flex:0.7;">
                <div class="pqa-metric-label">Result</div>
                <div class="pqa-overall-badge {_ws_overall_badge}" style="margin-top:0.6rem;font-size:0.85rem;">{_ws_overall_label}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        # Compliance table
        if not _ws_ev.empty:
            st.markdown(f"""
            <div class="pqa-section-header">
              <div class="pqa-section-bar"></div>
              <span class="pqa-section-title">Compliance Results</span>
              <span class="pqa-section-badge {_ws_bc}">{_ws_bt}</span>
            </div>""", unsafe_allow_html=True)

            _ws_src  = _ws_ev
            _ws_disp = pd.DataFrame()
            if "Timestamp" in _ws_src.columns:
                def _ws_fmt_ts(row):
                    s = row["Timestamp"]
                    e = row.get("End_Timestamp", s)
                    return s.strftime("%H:%M:%S") if (pd.isna(e) or s == e) else s.strftime("%H:%M:%S") + f"–{e.strftime('%H:%M:%S')}"
                _ws_disp["Event Time"] = _ws_src.apply(_ws_fmt_ts, axis=1)
            if "dKw" in _ws_src.columns:
                _ws_disp["Load Change (kW)"] = _ws_src["dKw"].apply(lambda x: f"+{x:.1f}" if x > 0 else f"{x:.1f}")
            if "V_dev" in _ws_src.columns:
                _wnom = _ws_cfg.nominal_voltage
                _ws_disp["Voltage Deviation"] = _ws_src["V_dev"].apply(
                    lambda v: f"{v:.1f} V ({(v - _wnom) / _wnom * 100:+.2f}%)" if pd.notna(v) else "—")
            if "V_rec_s" in _ws_src.columns:
                _ws_disp["V Recovery (s)"] = _ws_src["V_rec_s"].apply(
                    lambda v: f"{v:.2f}" if pd.notna(v) else "—")
            if "F_dev" in _ws_src.columns:
                _ws_disp["Freq Deviation"] = _ws_src["F_dev"].apply(
                    lambda v: f"{v:.3f} Hz ({(v - _ws_cfg.nominal_frequency) / _ws_cfg.nominal_frequency * 100:+.3f}%)" if pd.notna(v) else "—")
            if "F_rec_s" in _ws_src.columns:
                _ws_disp["F Recovery (s)"] = _ws_src["F_rec_s"].apply(
                    lambda v: f"{v:.2f}" if pd.notna(v) else "—")
            if "Compliance_Status" in _ws_src.columns:
                _ws_disp["Compliance Status"] = _ws_src["Compliance_Status"]

            _ws_tbl_h = 60 + len(_ws_disp) * 60
            st.components.v1.html(_render_compliance_html(_ws_disp), height=_ws_tbl_h, scrolling=False)

        # Time-series plots
        if _ws_gp:
            st.markdown("""
            <div class="pqa-section-header">
              <div class="pqa-section-bar" style="background:#0891b2;"></div>
              <span class="pqa-section-title">Time-Series Plots</span>
            </div>""", unsafe_allow_html=True)
            import re as _re_ws
            _ws_plot_tabs = st.tabs([n.replace("Avg_", "").replace("_", " ") for n in _ws_gp.keys()])
            for _wt, (_wn, _wp) in zip(_ws_plot_tabs, _ws_gp.items()):
                with _wt:
                    if _wp.endswith(".svg") and os.path.exists(_wp):
                        with open(_wp, "r", encoding="utf-8") as _wf:
                            _wsvg = _wf.read()
                        _wsvg = _re_ws.sub(r'(<svg\b[^>]*?)\s+width="[^"]*"',  r'\1 width="100%"', _wsvg, count=1)
                        _wsvg = _re_ws.sub(r'(<svg\b[^>]*?)\s+height="[^"]*"', r'\1',              _wsvg, count=1)
                        st.components.v1.html(f'<div style="width:100%">{_wsvg}</div>', height=480, scrolling=False)
                    elif os.path.exists(_wp):
                        st.image(_wp, use_container_width=True)

        # Temperature & Pressure plots
        _ws_tpp = st.session_state.get("ws_tp_paths", {})
        if _ws_tpp:
            st.markdown("""
            <div class="pqa-section-header">
              <div class="pqa-section-bar" style="background:#ea580c;"></div>
              <span class="pqa-section-title">Temperatures &amp; Pressures</span>
            </div>""", unsafe_allow_html=True)
            import re as _re_tp
            _tp_tab_labels = [k.replace("_", " ") for k in _ws_tpp.keys()]
            _tp_tabs = st.tabs(_tp_tab_labels)
            for _tpt, _tpp in zip(_tp_tabs, _ws_tpp.values()):
                with _tpt:
                    if _tpp.endswith(".svg") and os.path.exists(_tpp):
                        with open(_tpp, "r", encoding="utf-8") as _tpf:
                            _tpsvg = _tpf.read()
                        _tpsvg = _re_tp.sub(r'(<svg\b[^>]*?)\s+width="[^"]*"',  r'\1 width="100%"', _tpsvg, count=1)
                        _tpsvg = _re_tp.sub(r'(<svg\b[^>]*?)\s+height="[^"]*"', r'\1',              _tpsvg, count=1)
                        st.components.v1.html(f'<div style="width:100%">{_tpsvg}</div>', height=480, scrolling=False)
                    elif os.path.exists(_tpp):
                        st.image(_tpp, use_container_width=True)

        # Event snapshots
        if _ws_sp:
            st.markdown("""
            <div class="pqa-section-header">
              <div class="pqa-section-bar" style="background:#9333ea;"></div>
              <span class="pqa-section-title">Event Snapshots</span>
            </div>""", unsafe_allow_html=True)
            import re as _re_ws2
            for _wsi, _wsp in enumerate(_ws_sp):
                if not os.path.exists(_wsp):
                    continue
                _ws_ev_row  = _ws_ev.iloc[_wsi] if _wsi < len(_ws_ev) else None
                _ws_ev_ts   = _ws_ev_row["Timestamp"].strftime("%H:%M:%S") if _ws_ev_row is not None else f"Event {_wsi+1}"
                _ws_ev_dkw  = float(_ws_ev_row["dKw"]) if (_ws_ev_row is not None and "dKw" in _ws_ev_row) else 0.0
                _ws_ev_lbl  = f"{'▲' if _ws_ev_dkw > 0 else '▼'} {abs(_ws_ev_dkw):.0f} kW"
                _ws_compl   = _ws_ev_row.get("Compliance_Status", "—") if _ws_ev_row is not None else "—"
                _ws_cc      = "#16a34a" if _ws_compl == "Pass" else "#dc2626" if _ws_compl == "Fail" else "#64748b"
                with st.expander(f"Event {_wsi+1} · {_ws_ev_ts} · {_ws_ev_lbl}", expanded=(_wsi == 0)):
                    st.markdown(f'<span style="color:{_ws_cc};font-weight:700;font-size:13px;">{_ws_compl}</span>', unsafe_allow_html=True)
                    if _wsp.endswith(".svg") and os.path.exists(_wsp):
                        with open(_wsp, "r", encoding="utf-8") as _wsf2:
                            _wsnap = _wsf2.read()
                        _wsnap = _re_ws2.sub(r'(<svg\b[^>]*?)\s+width="[^"]*"',  r'\1 width="100%"', _wsnap, count=1)
                        _wsnap = _re_ws2.sub(r'(<svg\b[^>]*?)\s+height="[^"]*"', r'\1',              _wsnap, count=1)
                        st.components.v1.html(f'<div style="width:100%">{_wsnap}</div>', height=520, scrolling=False)
                    elif os.path.exists(_wsp):
                        st.image(_wsp, use_container_width=True)

    # ── WinScope Report Generation ────────────────────────────
    if ws_generate_clicked and st.session_state.get("ws_analysis_done"):
        if selected_template_path is not None or html_template_str is not None:
            _ws_rpt_client = st.session_state.get("ws_client_name", "report")
            _ws_rpt_cfg    = st.session_state.get("ws_config")
            _ws_rpt_prog   = st.empty()
            _ws_pdf_log    = {}
            _ws_success    = False
            try:
                _show_progress_popup(_ws_rpt_prog, 10, "Building content map…", "Generating Report")
                _ws_config_vals = {
                    "report_title": report_title,
                    "pqa_serial": pqa_serial,
                    "gen_sn": gen_sn,
                    "site_address": site_address,
                    "custom_text": custom_text,
                }
                _show_progress_popup(_ws_rpt_prog, 35, "Mapping placeholders…", "Generating Report")
                _ws_p_map = get_placeholder_map(
                    _ws_rpt_client, _ws_config_vals,
                    df=st.session_state.get("ws_df_raw"),
                    graph_dir=st.session_state.get("ws_graph_dir", GRAPH_DIR),
                    snapshot_dir=st.session_state.get("ws_snap_dir", SNAPSHOT_DIR),
                    image_dir=st.session_state.get("ws_img_dir", IMAGE_DIR),
                )
                _ws_output_base = os.path.join(OUTPUT_BASE, report_filename)
                _ws_entry = {"name": report_filename, "files": {}}

                if report_format == "Word Template":
                    _show_progress_popup(_ws_rpt_prog, 50, "Injecting content into Word template…", "Generating Report")
                    _ws_docx_path = generate_docx(selected_template_path, _ws_p_map, output_name=_ws_output_base)
                    if download_format in ("Word (.docx)", "Word+PDF"):
                        with open(_ws_docx_path, "rb") as _wf:
                            _ws_entry["files"]["docx"] = _wf.read()
                    if download_format in ("PDF", "Word+PDF"):
                        _show_progress_popup(_ws_rpt_prog, 75, "Converting to PDF…", "Generating Report")
                        _ws_pdf_path = f"{_ws_output_base}.pdf"
                        _ws_pdf_ok, _ws_pdf_log_txt = convert_to_pdf(_ws_docx_path, _ws_pdf_path)
                        _ws_pdf_log["log"] = _ws_pdf_log_txt
                        _ws_pdf_log["ok"] = _ws_pdf_ok
                        if _ws_pdf_ok:
                            with open(_ws_pdf_path, "rb") as _wf:
                                _ws_entry["files"]["pdf"] = _wf.read()
                else:
                    _show_progress_popup(_ws_rpt_prog, 50, "Injecting content into HTML template…", "Generating Report")
                    _ws_html_result = generate_html_report(_ws_p_map, html_template_str, output_name=_ws_output_base)
                    if download_format in ("HTML", "HTML+PDF"):
                        with open(_ws_html_result["html"], "rb") as _wf:
                            _ws_entry["files"]["html"] = _wf.read()
                    if download_format in ("PDF", "HTML+PDF"):
                        _show_progress_popup(_ws_rpt_prog, 75, "Converting to PDF…", "Generating Report")
                        _ws_pdf_log["ok"] = "pdf" in _ws_html_result
                        _ws_pdf_log["log"] = _ws_html_result.get("pdf_log", "")
                        if "pdf" in _ws_html_result:
                            with open(_ws_html_result["pdf"], "rb") as _wf:
                                _ws_entry["files"]["pdf"] = _wf.read()

                _rpts = st.session_state.get("generated_reports", [])
                _rpts.append(_ws_entry)
                st.session_state["generated_reports"] = _rpts
                _show_progress_popup(_ws_rpt_prog, 100, "Done!", "Generating Report")
                _ws_rpt_prog.empty()
                _ws_success = True
            except Exception as _ws_rpt_exc:
                _ws_rpt_prog.empty()
                log.exception(f"WinScope report generation failed: {_ws_rpt_exc}")
                st.error(f"Report generation failed: {_ws_rpt_exc}")

            if _ws_pdf_log.get("log"):
                with st.expander("PDF converter log", expanded=not _ws_pdf_log.get("ok")):
                    st.code(_ws_pdf_log["log"], language="text")
            if _ws_success:
                st.rerun()


    elif _selected_ws_path is None:
        st.markdown("""
        <div style="text-align:center;padding:4rem 2rem;border:2px dashed #e2e8f0;border-radius:12px;color:#94a3b8;margin-top:2rem;">
          <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom:1rem;"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
          <p style="margin:0;font-size:1rem;font-weight:600;">Upload a WinScope .xls file to begin</p>
          <p style="margin:0.5rem 0 0;font-size:0.85rem;">High-resolution data · No interpolation · Full compliance analysis</p>
        </div>
        """, unsafe_allow_html=True)



# ============================================================
# SET POINT COMPARISON TAB
# ============================================================
elif _active_tab_main == "setpoint":
    from ecu_parser import parse_file as _ecu_parse_file
    from ecu_csv_parser import parse_csv_file as _ecu_parse_csv
    from ecu_multi_comparator import compare_all_files as _ecu_compare_all
    from ecu_csv_comparator import compare_csv_files as _ecu_compare_csv
    import tempfile as _tempfile

    st.markdown("""
    <div style="display:flex;align-items:flex-start;gap:14px;margin-bottom:1.5rem;padding-bottom:1.25rem;border-bottom:2px solid #e2e8f0;">
      <div style="width:42px;height:42px;background:linear-gradient(135deg,#7c3aed,#9333ea);border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 2px 8px rgba(147,51,234,0.35);">
        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
      </div>
      <div>
        <h2 style="margin:0;padding:0;border:none;font-size:1.4rem;font-weight:800;color:#0f172a;letter-spacing:-0.03em;line-height:1.15;">Set Point Comparison</h2>
        <p style="margin:0.2rem 0 0;font-size:0.8rem;color:#64748b;font-weight:400;">Compare ECU parameter files (XLS/XLSX) and ComAp configuration files (CSV) · Highlight differences across multiple units</p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    _sp_col1, _sp_col2, _sp_col3 = st.columns(3)
    with _sp_col1:
        st.subheader("XLS Files")
        _sp_xls_files = st.file_uploader(
            "Select .XLS files", type=["xls"], accept_multiple_files=True,
            key="sp_xls_uploader", help="Upload ECU parameter .XLS files (old format)"
        )
    with _sp_col2:
        st.subheader("XLSX Files")
        _sp_xlsx_files = st.file_uploader(
            "Select .XLSX files", type=["xlsx"], accept_multiple_files=True,
            key="sp_xlsx_uploader", help="Upload ECU parameter .XLSX files (modern format)"
        )
    with _sp_col3:
        st.subheader("CSV Files")
        _sp_csv_files = st.file_uploader(
            "Select .CSV files", type=["csv"], accept_multiple_files=True,
            key="sp_csv_uploader", help="Upload ComAp configuration .CSV files"
        )

    st.divider()

    _sp_tab1, _sp_tab2, _sp_tab3 = st.tabs(["XLS Comparison", "XLSX Comparison", "CSV Comparison"])

    def _sp_run_xls_xlsx(files_list, label, download_prefix):
        if files_list and len(files_list) >= 2:
            if st.button(f"Run {label} Comparison", key=f"sp_{label.lower()}_run", type="primary", use_container_width=True):
                with st.spinner(f"Loading and comparing {label} files..."):
                    try:
                        files_data = {}
                        with _tempfile.TemporaryDirectory() as _tmpdir:
                            for _uf in files_list:
                                _tp = os.path.join(_tmpdir, _uf.name)
                                with open(_tp, "wb") as _fh:
                                    _fh.write(_uf.getbuffer())
                                files_data[Path(_uf.name).stem] = _ecu_parse_file(_tp)

                            _diffs = _ecu_compare_all(files_data)

                        if _diffs:
                            _df = pd.DataFrame(_diffs)
                            st.success(f"Found **{len(_df)}** difference locations across **{len(files_list)}** files")

                            _sheet_filter = st.multiselect(
                                "Filter by Sheet", ["Parameter", "Val_2D", "Val_3D"],
                                default=["Parameter", "Val_2D", "Val_3D"],
                                key=f"sp_{label.lower()}_sheet_filter"
                            )
                            _fdf = _df[_df["Sheet"].isin(_sheet_filter)].copy()
                            st.subheader(f"Differences ({len(_fdf)} locations)")

                            _file_cols = [c for c in _fdf.columns if c not in ["Sheet", "Nr", "Name", "Location"]]
                            _col_cfg = {
                                "Sheet": st.column_config.TextColumn(width="small"),
                                "Nr": st.column_config.TextColumn(width="small"),
                                "Name": st.column_config.TextColumn(width="medium"),
                                "Location": st.column_config.TextColumn(width="small"),
                            }
                            for _fc in _file_cols:
                                _col_cfg[_fc] = st.column_config.TextColumn(width="small")

                            st.dataframe(_fdf, use_container_width=True, hide_index=True, column_config=_col_cfg)
                            st.download_button(
                                "📥 Download as CSV", data=_fdf.to_csv(index=False),
                                file_name=f"{download_prefix}_differences.csv", mime="text/csv",
                                key=f"sp_{label.lower()}_download"
                            )
                        else:
                            st.info("No differences found — all files are identical.")
                    except Exception as _e:
                        st.error(f"Error during {label} comparison: {str(_e)}")
        else:
            st.markdown("""
            <div style="text-align:center;padding:3rem 2rem;border:2px dashed #e2e8f0;border-radius:12px;color:#94a3b8;margin-top:1rem;">
              <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom:0.75rem;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              <p style="margin:0;font-size:0.95rem;font-weight:600;">Upload at least 2 files to compare</p>
            </div>
            """, unsafe_allow_html=True)

    with _sp_tab1:
        _sp_run_xls_xlsx(_sp_xls_files, "XLS", "xls")
    with _sp_tab2:
        _sp_run_xls_xlsx(_sp_xlsx_files, "XLSX", "xlsx")

    with _sp_tab3:
        if _sp_csv_files and len(_sp_csv_files) >= 2:
            if st.button("Run CSV Comparison", key="sp_csv_run", type="primary", use_container_width=True):
                with st.spinner("Loading and comparing CSV files..."):
                    try:
                        _csv_data = {}
                        with _tempfile.TemporaryDirectory() as _tmpdir:
                            for _uf in _sp_csv_files:
                                _tp = os.path.join(_tmpdir, _uf.name)
                                with open(_tp, "wb") as _fh:
                                    _fh.write(_uf.getbuffer())
                                _csv_data[Path(_uf.name).stem] = _ecu_parse_csv(_tp)

                            _diffs = _ecu_compare_csv(_csv_data)

                        if _diffs:
                            _df = pd.DataFrame(_diffs)
                            st.success(f"Found **{len(_df)}** difference locations across **{len(_sp_csv_files)}** files")

                            _groups = _df["Group"].unique().tolist()
                            _group_filter = st.multiselect(
                                "Filter by Group", _groups, default=_groups, key="sp_csv_group_filter"
                            )
                            _fdf = _df[_df["Group"].isin(_group_filter)].copy()
                            st.subheader(f"Differences ({len(_fdf)} locations)")

                            _file_cols = [c for c in _fdf.columns if c not in ["Group", "Sub-group", "Name", "Dimension"]]
                            _col_cfg = {
                                "Group": st.column_config.TextColumn(width="small"),
                                "Sub-group": st.column_config.TextColumn(width="small"),
                                "Name": st.column_config.TextColumn(width="medium"),
                                "Dimension": st.column_config.TextColumn(width="small"),
                            }
                            for _fc in _file_cols:
                                _col_cfg[_fc] = st.column_config.TextColumn(width="small")

                            st.dataframe(_fdf, use_container_width=True, hide_index=True, column_config=_col_cfg)
                            st.download_button(
                                "📥 Download as CSV", data=_fdf.to_csv(index=False),
                                file_name="csv_differences.csv", mime="text/csv",
                                key="sp_csv_download"
                            )
                        else:
                            st.info("No differences found — all files are identical.")
                    except Exception as _e:
                        st.error(f"Error during CSV comparison: {str(_e)}")
        else:
            st.markdown("""
            <div style="text-align:center;padding:3rem 2rem;border:2px dashed #e2e8f0;border-radius:12px;color:#94a3b8;margin-top:1rem;">
              <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom:0.75rem;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              <p style="margin:0;font-size:0.95rem;font-weight:600;">Upload at least 2 CSV files to compare</p>
            </div>
            """, unsafe_allow_html=True)


# ============================================================
# DEV MODE SAVE — persist settings to JSON after every full render
# ============================================================
if _ds.get("dev_mode"):
    # Collect values from already-keyed widgets via session_state
    for _k in ("fri_upper", "fri_lower", "frd_upper", "frd_lower",
                "rated_load_input", "expected_steps_input",
                "nom_v_preset", "nom_v_custom", "report_format"):
        _ds[_k] = st.session_state.get(_k, _DEV_DEFAULTS.get(_k))
    _ds["_tf_csv_path"] = st.session_state.get("_tf_csv_path", "")
    _ds["tf_start_text"] = st.session_state.get(_TF_START_TEXT, "")
    _ds["tf_end_text"]   = st.session_state.get(_TF_END_TEXT, "")
    _save_dev_settings(_ds)


# ============================================================
# DEBUG LOG PANEL — only visible if Dev Mode is enabled
# ============================================================
with st.sidebar:
    if st.session_state.get("_ds", {}).get("dev_mode", False):
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
