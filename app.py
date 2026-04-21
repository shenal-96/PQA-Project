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

from analysis import AnalysisConfig, load_and_prepare_csv, perform_analysis, check_compliance, calculate_recovery_time
from visualizations import (
    generate_plots,
    generate_all_snapshots,
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

# --- Help assets (screenshots shown in the Help dialog) ---
HELP_ASSETS_DIR = os.path.join(_APP_DIR, "assets", "help")
os.makedirs(HELP_ASSETS_DIR, exist_ok=True)

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


def _help_image(filename: str, caption: str | None = None):
    """Render a help screenshot if present in assets/help/, otherwise a placeholder."""
    path = os.path.join(HELP_ASSETS_DIR, filename)
    if os.path.exists(path):
        st.image(path, caption=caption, use_container_width=True)
    else:
        st.info(
            f"Screenshot placeholder — save the corresponding image as "
            f"`assets/help/{filename}` and it will appear here."
        )


def _render_help_getting_started():
    st.markdown("#### Generating the CSV from PQone")
    st.caption(
        "The PQA tool analyses data exported from PQone as a Trend Graph CSV. "
        "Follow the steps below to produce a correctly-formatted file."
    )

    st.markdown("**Step 1 — Open the PQA data with PQone**")
    st.write(
        "Launch PQone on the PC where your power-quality recording is stored "
        "and open the project that contains the test run of interest."
    )

    st.markdown("**Step 2 — Select Line-to-Line voltage**")
    st.write(
        "In the Option dialog (Δ = V/PF/THD tab), set Urms to `Line – Line`. "
        "This ensures the exported voltages are line-to-line values."
    )
    _help_image("step2_select_ll_voltage.png",
                caption="Step 2 — Line-to-Line voltage selection in PQone")

    st.markdown("**Step 3 — Select \"Trend Graph\" from the CSV export options**")
    st.write(
        "Click the CSV export icon on the PQone toolbar and choose **Trend Graph** "
        "from the dropdown."
    )
    _help_image("step3_trend_graph_export.png",
                caption="Step 3 — Choose Trend Graph from the CSV export menu")

    st.markdown("**Step 4 — Make the following selections and click OK to save the CSV file**")
    st.write(
        "In the *Export csv file – Trend Graph* dialog, tick **U / I**, **Frequency**, "
        "**Harmonics – Trend**, **Power**, and **Energy** under *Trend Graph Tabs*. "
        "Leave *Displayed Items* selected under *Output Items*. Click **OK** to save the CSV."
    )
    st.info(
        "The CSV file name is used to auto-populate the `{{report_title}}` placeholder "
        "in the uploaded report template (editable later). Name the file after the test "
        "that was conducted — e.g. `ISO 8528 Step Load`."
    )
    _help_image("step4_export_dialog.png",
                caption="Step 4 — Export CSV dialog selections")


def _render_help_running_analysis():
    st.markdown("#### Running the analysis")
    st.write(
        "1. **Upload your CSV** in the sidebar under *Data Files*. Uploaded files "
        "persist between sessions, so you only need to upload each CSV once."
    )
    st.write(
        "2. **Select the CSV** from the dropdown. The app auto-detects the "
        "recording's time range and shows it beneath the preview."
    )
    st.write(
        "3. **Set Acceptance Criteria**. Tick *Apply ISO 8528 Presets* to use the "
        "standard values, or untick to edit the thresholds manually. Nominal "
        "voltage and frequency are under *Display Options*."
    )
    st.write(
        "4. **(Optional) Time Filter** — narrow the analysis window using the "
        "Start / End sliders or type HH:MM:SS directly."
    )
    st.write(
        "5. **Click ⚡ Run Analysis**. The app detects load-step events, "
        "calculates voltage / frequency exit and recovery times, and renders "
        "the compliance table, time-series plots, and per-event snapshots."
    )
    st.write(
        "6. **Review events** by expanding each snapshot. You can manually "
        "override the band-exit or recovery crossing for any event; the table "
        "and report refresh automatically."
    )


def _render_help_generating_reports():
    st.markdown("#### Generating the report")
    st.write(
        "1. Choose **Report Format** in the sidebar — *Word Template* or "
        "*HTML Template*."
    )
    st.write(
        "2. **Word Template** — upload a `.docx` containing placeholders such as "
        "`{{report_title}}`, `{{generator_sn}}`, `{{site_address}}`, "
        "`{{custom_text}}`, `{{compliance_table}}`, `{{voltage_graph}}`, "
        "`{{frequency_graph}}`, `{{kw_graph}}`, and the per-event snapshot "
        "placeholders. The app injects graphs, snapshots, and the compliance "
        "table image into those placeholders."
    )
    st.write(
        "3. **HTML Template** — edit the built-in HTML template inline; "
        "placeholders match the Word pipeline. Click *Reset* to restore the "
        "default template."
    )
    st.write(
        "4. Fill in the **Report Details** fields (Report Title, PQA Serial No., "
        "Generator Serial Number, Site Address, Custom Text Field) — these feed "
        "directly into the template placeholders."
    )
    st.write(
        "5. Click **Generate Report**. The app produces a `.docx` (Word) or "
        "`.html` (HTML) file plus a `.pdf` rendering. Both files are offered as "
        "downloads and kept under *Previous Reports* for the session."
    )
    st.caption(
        "PDF conversion uses LibreOffice (preferred), WeasyPrint, or reportlab as "
        "fallbacks. On Streamlit Cloud, LibreOffice is installed via `packages.txt`; "
        "on a local Mac install it with `brew install --cask libreoffice`."
    )


def _render_help_parameters():
    st.markdown("#### Configuration parameter reference")
    st.caption("Wording matches the sidebar labels.")

    st.markdown("##### Acceptance Criteria")
    st.markdown(
        "- **Apply ISO 8528 Presets** — loads the ISO 8528 standard acceptance "
        "values (Load Threshold 50 kW, Voltage Tolerance 1%, Voltage Recovery 4 s, "
        "Max Voltage Dev 15%, Frequency Tolerance 0.5%, Frequency Recovery 3 s, "
        "Max Frequency Dev 7%, standard frequency recovery bands). When ticked "
        "the numeric fields are locked.\n"
        "- **Deviation Limits on Main Graphs** — overlays the *maximum allowed* "
        "voltage / frequency deviation bounds (±Max Voltage Dev %, ±Max Frequency Dev %) "
        "on the Voltage and Frequency time-series plots.\n"
        "- **Show Limits on Snapshots** — overlays the compliance band "
        "(Voltage Tolerance / frequency recovery bands) on each event snapshot.\n"
        "- **Show Intersection Points** — overlays exact band-exit (orange ★) "
        "and recovery (lime ★) crossing markers on event snapshots, with the "
        "compliance band used for that event. Useful for verifying computed "
        "recovery times against the waveform.\n"
        "- **Show Event Detection (De-bugging)** — adds amber event-timestamp "
        "lines and threshold annotations to the plots.\n"
        "- **Detection Window (s)** — time window used to group consecutive "
        "load step rows into a single event (default 5 s). Prevents a ramp-style "
        "load change from being counted as multiple events.\n"
        "- **Snapshot Window (s)** — seconds shown either side of each event in "
        "snapshots. Also sets the window used to find peak voltage / frequency "
        "deviation (default 10 s).\n"
        "- **Recovery Verify Window (s)** *(Dev Mode)* — after a recovery "
        "candidate is found, verify the signal stays in-band for this many "
        "seconds before accepting it (default 6 s). Handles oscillating waveforms."
    )
    st.markdown(
        "- **Load Threshold (kW)** — minimum |ΔkW| between consecutive samples "
        "required to register a load-step event.\n"
        "- **Voltage Tolerance (%)** — steady-state voltage band, as a percentage "
        "of nominal voltage. Used for the recovery (re-entry) test.\n"
        "- **Voltage Recovery (s)** — maximum allowed time from band-exit to "
        "sustained re-entry for the event to pass.\n"
        "- **Max Voltage Dev (%)** — maximum allowed instantaneous deviation "
        "from nominal voltage during the event transient.\n"
        "- **Frequency Tolerance (%)** — symmetric steady-state frequency band "
        "used when asymmetric recovery bands are not overridden.\n"
        "- **Frequency Recovery (s)** — maximum allowed time from band-exit to "
        "sustained re-entry for the event to pass.\n"
        "- **Max Frequency Dev (%)** — maximum allowed instantaneous deviation "
        "from nominal frequency during the event transient."
    )
    st.markdown(
        "- **Frequency Recovery Bands (Hz)** — the asymmetric recovery band "
        "used for frequency compliance. *Load Increase* (generator slows) uses "
        "a lower band offset from nominal; *Load Decrease* (generator speeds up) "
        "uses an upper band. Defaults: increase `[49.75, 50.50]` Hz, "
        "decrease `[49.50, 50.25]` Hz."
    )

    st.markdown("##### Rated Load")
    st.markdown(
        "- **Rated Load (kW)** — optional. When set, each event's load change "
        "is expressed as a percentage of rated load.\n"
        "- **No. Expected Load Steps** — optional. If set, a warning is shown "
        "when the number of detected events does not match this count."
    )

    st.markdown("##### Display Options")
    st.markdown(
        "- **Nominal Voltage** — preset (415 V LV, 690 V MV-LV, 11 000 V) or "
        "Custom. All compliance bounds are expressed relative to this value "
        "(line-to-line).\n"
        "- **Nominal Frequency (Hz)** — target generator frequency (default 50 Hz).\n"
        "- **CSV Voltage Columns** — how the CSV's voltage columns are interpreted:\n"
        "  - *Auto-detect (by column names)* — `U12/U23/U31` = L-L, "
        "`U1/U2/U3` = L-N (multiplied by √3).\n"
        "  - *Line-to-Line — use as-is* — no scaling applied.\n"
        "  - *Line-to-Neutral — convert ×√3 to L-L* — every voltage column is "
        "scaled up by √3. Compliance is always checked against L-L."
    )

    st.markdown("##### Time Filter")
    st.markdown(
        "- **Start Time / End Time** — text inputs (HH:MM:SS) with companion "
        "sliders. The analysis is restricted to rows within this window.\n"
        "- The ↺ reset buttons restore the auto-detected full CSV range."
    )

    st.markdown("##### Report Details & Generate Report")
    st.markdown(
        "- **Report Title / PQA Serial No. / Generator Serial Number / "
        "Site Address / Custom Text Field** — free-text fields written into the "
        "matching template placeholders.\n"
        "- **Report Format** — *Word Template* (upload `.docx`, docx+pdf output) "
        "or *HTML Template* (edit the built-in template inline, html+pdf output)."
    )


def _render_help_methodology():
    st.markdown("#### How the analysis works")

    st.markdown("##### 1. CSV load & voltage scaling")
    st.write(
        "Rows are parsed, timestamps normalised, and voltage columns scaled to "
        "line-to-line as selected under *CSV Voltage Columns*. L-N columns "
        "(`U1/U2/U3_rms_AVG`) are multiplied by √3."
    )
    st.latex(r"V_{LL} = \sqrt{3}\cdot V_{LN}")

    st.markdown("##### 2. Event detection")
    st.write(
        "Active power (`Avg_kW`) is differenced sample-to-sample. Rows where "
        "`|ΔkW| ≥ Load Threshold (kW)` are load-step candidates. Consecutive "
        "candidate rows within *Detection Window (s)* are merged into a single "
        "event."
    )
    st.latex(r"\text{event}(t) \iff |\Delta \text{kW}(t)| \geq \text{Load Threshold}")

    st.markdown("##### 3. 100 ms interpolation grid (df_interp)")
    st.write(
        "The raw logger data (~1 s/sample) is linearly interpolated to a "
        "100 ms grid. This finer grid is used **only** for computing exit and "
        "recovery crossings — deviation values, plots, and snapshots always use "
        "the raw measured data."
    )

    st.markdown("##### 4. Peak deviation (V_dev, F_dev)")
    st.write(
        "Within ±*Snapshot Window (s)* around each event, the peak measured "
        "voltage / frequency is extracted from the raw data:"
    )
    st.markdown(
        "- Load increase (`ΔkW > 0`) → signal dips → `V_dev = min(vals)`, "
        "`F_dev = min(vals)`\n"
        "- Load decrease (`ΔkW ≤ 0`) → signal rises → `V_dev = max(vals)`, "
        "`F_dev = max(vals)`"
    )
    st.write("Peak-deviation percentage shown in the compliance table:")
    st.latex(r"V_{\text{dev}}\% = \frac{|V_{\text{dev}} - V_{\text{nom}}|}{V_{\text{nom}}} \times 100")
    st.latex(r"F_{\text{dev}}\% = \frac{|F_{\text{dev}} - F_{\text{nom}}|}{F_{\text{nom}}} \times 100")

    st.markdown("##### 5. Compliance bands")
    st.write("Voltage tolerance band (used for the recovery re-entry test):")
    st.latex(r"[\,V_{\text{nom}}(1 - \tfrac{t_V}{100}),\ V_{\text{nom}}(1 + \tfrac{t_V}{100})\,]")
    st.write("Voltage maximum-deviation envelope (used for the peak-deviation test):")
    st.latex(r"[\,V_{\text{nom}}(1 - \tfrac{d_V}{100}),\ V_{\text{nom}}(1 + \tfrac{d_V}{100})\,]")
    st.write(
        "Frequency recovery bands are *asymmetric* — the band depends on load "
        "direction (generator governor response is not symmetric):"
    )
    st.markdown(
        "- Load increase → band `[freq_rec_lower_increase, freq_rec_upper_increase]` "
        "(default `[49.75, 50.50]` Hz).\n"
        "- Load decrease → band `[freq_rec_lower_decrease, freq_rec_upper_decrease]` "
        "(default `[49.50, 50.25]` Hz)."
    )

    st.markdown("##### 6. Exit time")
    st.write(
        "`calculate_exit_time` scans **backwards** from the event timestamp on "
        "`df_interp` up to 30 s. It finds the last in-band point and the first "
        "subsequent out-of-band point, then linearly interpolates the exact "
        "crossing timestamp. Returns `None` if the signal was already in-band "
        "at the event (no excursion) or out-of-band for the entire lookback."
    )

    st.markdown("##### 7. Recovery time")
    st.write(
        "`calculate_recovery_time` scans **forward** from the exit timestamp on "
        "`df_interp`. It looks for a *sustained* in-band window of "
        "`sustain_s = 0.3 s` (3 consecutive 100 ms samples). When found, the "
        "candidate is recorded and verification continues for "
        "*Recovery Verify Window (s)*. If the signal exits the band again "
        "during verification (oscillation), the candidate is discarded and the "
        "search resumes. The exact re-entry crossing is linearly interpolated."
    )
    st.latex(r"t_{\text{recovery}} = t_{\text{re-entry crossing}} - t_{\text{exit crossing}}")
    st.caption(
        "Recovery is measured from the exact band-exit to the exact band-re-entry, "
        "not from the load-change timestamp."
    )

    st.markdown("##### 8. Pass / Fail per event")
    st.write("An event passes compliance when **all** of:")
    st.markdown(
        "- Peak voltage deviation ≤ *Max Voltage Dev (%)*.\n"
        "- Voltage recovery time ≤ *Voltage Recovery (s)*.\n"
        "- Peak frequency deviation ≤ *Max Frequency Dev (%)*.\n"
        "- Frequency recovery time ≤ *Frequency Recovery (s)*.\n"
        "- Signal was not already out-of-band when the event began "
        "(*not-recovered* flag)."
    )


@st.dialog("PQA — Help & Documentation", width="large")
def show_help_dialog():
    st.caption(
        "Everything you need to know to run a compliance analysis, from "
        "exporting the CSV to generating the final report."
    )
    tab_start, tab_run, tab_report, tab_params, tab_method = st.tabs([
        "Getting Started",
        "Running Analysis",
        "Generating Reports",
        "Parameters",
        "How it Works",
    ])
    with tab_start:
        _render_help_getting_started()
    with tab_run:
        _render_help_running_analysis()
    with tab_report:
        _render_help_generating_reports()
    with tab_params:
        _render_help_parameters()
    with tab_method:
        _render_help_methodology()


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


# nom_v and nom_f are set by the sidebar Display Options section below.

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
    show_limits = st.checkbox("Deviation Limits on Main Graphs", value=_ds.get("show_limits", False))
    show_limits_snapshots = st.checkbox("Show Limits on Snapshots", value=_ds.get("show_limits_snapshots", False))
    show_intersections = st.checkbox(
        "Show Intersection Points",
        value=_ds.get("show_intersections", False),
        help="Overlay the exact band-exit (orange ★) and recovery (lime ★) crossing markers on event snapshots, "
             "along with the compliance band limits used for each event. "
             "Useful for verifying that calculated recovery times match the waveform.",
    )
    show_debug = st.checkbox("Show Event Detection (De-bugging)", value=_ds.get("show_debug", False))
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
    _s_col, _s_rst = st.columns([7, 1])
    with _s_col:
        start_time_text = st.text_input(
            "Start Time", key=_TF_START_TEXT, placeholder="HH:MM:SS",
            help="Filter analysis to start from this time.",
        )
    with _s_rst:
        st.markdown('<div class="pqa-rst-btn"></div>', unsafe_allow_html=True)
        if st.button("↺", key="reset_start_time"):
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
        if st.button("↺", key="reset_end_time"):
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

    # ── 5. Run Analysis ───────────────────────────────────────
    run_clicked = False
    if selected_csv_path is not None:
        run_clicked = st.button("\u26a1 Run Analysis", type="primary", use_container_width=True)
    else:
        st.info("Upload CSV files above to begin.")

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
    _df_ev_check = st.session_state.get("df_events")
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

    generate_clicked = False
    analysis_ready = st.session_state.get("analysis_done")
    if report_format == "Word Template":
        if selected_template_path is not None and analysis_ready:
            generate_clicked = st.button("\U0001f4c4 Generate Report", type="primary",
                                         use_container_width=True, disabled=_btn_disabled)
        elif not analysis_ready:
            st.caption("Run analysis first to enable report generation.")
        else:
            st.caption("Upload a template above to generate a report.")
    else:  # HTML Template
        if analysis_ready:
            generate_clicked = st.button("\U0001f4c4 Generate Report", type="primary",
                                         use_container_width=True, disabled=_btn_disabled)
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
_title_col, _help_col = st.columns([11, 2], gap="small")
with _title_col:
    st.markdown("""
    <div style="display:flex;align-items:flex-start;gap:14px;padding-top:0.25rem;">
      <div style="width:42px;height:42px;background:linear-gradient(135deg,#1d4ed8,#2563eb);border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 2px 8px rgba(37,99,235,0.35);">
        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polyline></svg>
      </div>
      <div>
        <h1 style="margin:0;padding:0;border:none;font-size:1.65rem;font-weight:800;color:#0f172a;letter-spacing:-0.03em;line-height:1.15;">Power Quality Analysis</h1>
        <p style="margin:0.2rem 0 0;font-size:0.8rem;color:#64748b;font-weight:400;">ISO 8528 compliance · Load event detection · Recovery time analysis</p>
      </div>
    </div>
    """, unsafe_allow_html=True)
with _help_col:
    st.markdown('<div style="padding-top:0.75rem;"></div>', unsafe_allow_html=True)
    if st.button("❔ Help", key="open_help_dialog", use_container_width=True,
                 help="Step-by-step instructions, parameter glossary, and analysis methodology."):
        show_help_dialog()

st.markdown(
    '<div style="margin:0.25rem 0 1.5rem;border-bottom:2px solid #e2e8f0;"></div>',
    unsafe_allow_html=True,
)

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
            max_dev_v=v_max_dev, max_dev_f=f_max_dev,
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
