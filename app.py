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

from analysis import AnalysisConfig, load_and_prepare_csv, perform_analysis
from visualizations import (
    generate_plots,
    generate_all_snapshots,
    save_compliance_table_as_image,
)
from report import get_placeholder_map, inject_images_to_word, generate_report

# --- Page Config ---
st.set_page_config(
    page_title="PQA - Power Quality Analysis",
    page_icon="\u26a1",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Output directories ---
OUTPUT_BASE = "output"
GRAPH_DIR = os.path.join(OUTPUT_BASE, "Graphs")
SNAPSHOT_DIR = os.path.join(OUTPUT_BASE, "Snapshots")
IMAGE_DIR = os.path.join(OUTPUT_BASE, "Images")
TEMPLATE_DIR = os.path.join(OUTPUT_BASE, "Template")


def init_output_dirs():
    """Create/clean output directories."""
    for d in [GRAPH_DIR, SNAPSHOT_DIR, IMAGE_DIR, TEMPLATE_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)


# --- Custom CSS ---
st.markdown("""
<style>
    .main .block-container { padding-top: 1.5rem; }
    div[data-testid="stSidebar"] { background-color: #f8fafc; }
    div[data-testid="stSidebar"] h1 { font-size: 1.3rem; }
    .stMetric { background-color: #f0f9ff; padding: 12px; border-radius: 8px; border: 1px solid #e0e7ff; }
    .pass-badge { color: #16a34a; font-weight: bold; font-size: 1.1em; }
    .fail-badge { color: #dc2626; font-weight: bold; font-size: 1.1em; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# SIDEBAR - Configuration
# ============================================================
with st.sidebar:
    st.title("\u2699\ufe0f Configuration")

    # --- Report Info ---
    st.subheader("Report Details")
    report_title = st.text_input("Report Title", placeholder="Enter report/client name")
    gen_sn = st.text_input("Generator Serial Number", placeholder="Enter Gen S/N")
    site_address = st.text_input("Site Address", placeholder="Enter site address")
    custom_text = st.text_input("Custom Text Field", placeholder="Enter custom info")

    st.divider()

    # --- Standards ---
    st.subheader("Acceptance Criteria")
    apply_iso = st.checkbox("Apply ISO 8528 Presets", value=False)

    if apply_iso:
        load_thresh = 50.0
        v_tol = 1.0
        v_rec = 4.0
        v_max_dev = 15.0
        f_tol = 0.5
        f_rec = 3.0
        f_max_dev = 7.0
        st.info("ISO 8528 presets applied")
        # Show values as read-only
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Load Threshold", f"{load_thresh} kW")
            st.metric("V Tolerance", f"{v_tol}%")
            st.metric("V Recovery", f"{v_rec}s")
            st.metric("V Max Dev", f"{v_max_dev}%")
        with col2:
            st.metric("F Tolerance", f"{f_tol}%")
            st.metric("F Recovery", f"{f_rec}s")
            st.metric("F Max Dev", f"{f_max_dev}%")
    else:
        col1, col2 = st.columns(2)
        with col1:
            load_thresh = st.number_input("Load Threshold (kW)", value=50.0, min_value=0.0, step=10.0)
            v_tol = st.number_input("Voltage Tolerance (%)", value=1.0, min_value=0.0, step=0.5)
            v_rec = st.number_input("Voltage Recovery (s)", value=4.0, min_value=0.0, step=0.5)
            v_max_dev = st.number_input("Max Voltage Dev (%)", value=15.0, min_value=0.0, step=1.0)
        with col2:
            f_tol = st.number_input("Frequency Tolerance (%)", value=0.5, min_value=0.0, step=0.1)
            f_rec = st.number_input("Frequency Recovery (s)", value=3.0, min_value=0.0, step=0.5)
            f_max_dev = st.number_input("Max Frequency Dev (%)", value=7.0, min_value=0.0, step=1.0)

    st.divider()

    # --- Display Options ---
    st.subheader("Display Options")
    show_limits = st.checkbox("Show Limits on Graphs", value=False)
    nom_v = st.number_input("Nominal Voltage (V)", value=415.0, step=1.0)
    nom_f = st.number_input("Nominal Frequency (Hz)", value=50.0, step=0.5)

    st.divider()

    # --- Time Filtering ---
    st.subheader("Time Filter")
    start_time = st.text_input("Start Time", placeholder="HH:MM:SS")
    end_time = st.text_input("End Time", placeholder="HH:MM:SS")


# ============================================================
# MAIN AREA
# ============================================================
st.title("\u26a1 Power Quality Analysis")
st.caption("Upload your CSV data, configure the acceptance criteria, and run the analysis.")

# --- Step 1: Upload CSV ---
st.header("1. Upload Data")
csv_file = st.file_uploader(
    "Upload CSV file from power quality recorder",
    type=["csv"],
    help="Supported formats: CSV files with columns like U1_rms_AVG, Freq_AVG, P_sum_AVG, etc.",
)

if csv_file is not None:
    client_name = os.path.splitext(csv_file.name)[0]
    if not report_title:
        report_title = client_name

    # Preview
    with st.expander("Preview uploaded data", expanded=False):
        preview_df = pd.read_csv(csv_file, sep=None, engine="python", nrows=10)
        st.dataframe(preview_df, use_container_width=True)
        csv_file.seek(0)  # Reset for actual processing

    # Auto-detect time range
    if not start_time or not end_time:
        try:
            temp_df = load_and_prepare_csv(csv_file)
            csv_file.seek(0)
            if not temp_df.empty:
                detected_start = temp_df["Timestamp"].min().strftime("%H:%M:%S")
                detected_end = temp_df["Timestamp"].max().strftime("%H:%M:%S")
                st.info(f"Detected time range: **{detected_start}** to **{detected_end}**")
                if not start_time:
                    start_time = detected_start
                if not end_time:
                    end_time = detected_end
        except Exception:
            pass

    # --- Step 2: Run Analysis ---
    st.header("2. Run Analysis")

    if st.button("Run Analysis", type="primary", use_container_width=True):
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
        )

        with st.spinner("Loading and processing data..."):
            df_raw = load_and_prepare_csv(csv_file, start_time=start_time, end_time=end_time)
            csv_file.seek(0)

            if df_raw.empty:
                st.error("No data found after loading/filtering. Check your CSV and time range.")
                st.stop()

            df_proc, df_events = perform_analysis(df_raw, config)

        # Store results in session state
        st.session_state["df_raw"] = df_raw
        st.session_state["df_proc"] = df_proc
        st.session_state["df_events"] = df_events
        st.session_state["client_name"] = client_name
        st.session_state["config"] = config
        st.session_state["analysis_done"] = True

        # --- Summary Metrics ---
        st.subheader("Data Summary")
        mcol1, mcol2, mcol3, mcol4 = st.columns(4)
        with mcol1:
            st.metric("Data Points", f"{len(df_proc):,}")
        with mcol2:
            st.metric("Events Detected", f"{len(df_events)}")
        with mcol3:
            if not df_events.empty and "Compliance_Status" in df_events.columns:
                pass_count = (df_events["Compliance_Status"] == "Pass").sum()
                st.metric("Pass", f"{pass_count}/{len(df_events)}")
        with mcol4:
            if not df_events.empty and "Compliance_Status" in df_events.columns:
                fail_count = (df_events["Compliance_Status"] == "Fail").sum()
                st.metric("Fail", f"{fail_count}/{len(df_events)}")

        # --- Generate Plots ---
        with st.spinner("Generating plots..."):
            graph_paths = generate_plots(
                df_proc, client_name, output_dir=GRAPH_DIR,
                show_limits=show_limits, nom_v=nom_v, nom_f=nom_f,
                tol_v=v_tol, tol_f=f_tol,
            )
        st.session_state["graph_paths"] = graph_paths

        # --- Generate Snapshots & Compliance Table ---
        snapshot_paths = []
        table_path = None
        if not df_events.empty:
            with st.spinner("Generating event snapshots..."):
                snapshot_paths = generate_all_snapshots(df_raw, df_events, client_name, output_dir=SNAPSHOT_DIR)

            with st.spinner("Generating compliance table..."):
                table_file = os.path.join(IMAGE_DIR, f"{client_name}_table.jpg")
                table_path = save_compliance_table_as_image(
                    df_events, table_file,
                    f"Compliance Report: {client_name}",
                    nom_v=nom_v, nom_f=nom_f,
                )
        else:
            st.warning("No load events detected above the threshold.")

        st.session_state["snapshot_paths"] = snapshot_paths
        st.session_state["table_path"] = table_path

        st.success(f"Analysis complete. {len(df_events)} events detected, "
                   f"{len(graph_paths)} plots and {len(snapshot_paths)} snapshots generated.")


# ============================================================
# RESULTS DISPLAY (persists after button click via session_state)
# ============================================================
if st.session_state.get("analysis_done"):
    df_events = st.session_state["df_events"]
    graph_paths = st.session_state.get("graph_paths", {})
    snapshot_paths = st.session_state.get("snapshot_paths", [])
    table_path = st.session_state.get("table_path")
    client_name = st.session_state["client_name"]
    config = st.session_state["config"]

    # --- Compliance Table ---
    if not df_events.empty:
        st.header("3. Compliance Results")

        # Interactive table
        display_df = df_events[
            [c for c in ["Timestamp", "dKw", "V_dev", "F_dev", "V_rec_s", "F_rec_s",
                         "Compliance_Status", "Failure_Reasons"] if c in df_events.columns]
        ].copy()
        if "Timestamp" in display_df.columns:
            display_df["Timestamp"] = display_df["Timestamp"].dt.strftime("%H:%M:%S")
        if "dKw" in display_df.columns:
            display_df["dKw"] = display_df["dKw"].round(1)
        if "V_dev" in display_df.columns:
            display_df["V_dev"] = (display_df["V_dev"] / config.nominal_voltage * 100).round(1)
        if "F_dev" in display_df.columns:
            display_df["F_dev"] = (display_df["F_dev"] / config.nominal_frequency * 100).round(1)
        if "V_rec_s" in display_df.columns:
            display_df["V_rec_s"] = display_df["V_rec_s"].round(1)
        if "F_rec_s" in display_df.columns:
            display_df["F_rec_s"] = display_df["F_rec_s"].round(1)

        display_df.columns = [
            c.replace("dKw", "Load Change (kW)")
             .replace("V_dev", "V Dev (%)")
             .replace("F_dev", "F Dev (%)")
             .replace("V_rec_s", "V Recovery (s)")
             .replace("F_rec_s", "F Recovery (s)")
             .replace("Compliance_Status", "Status")
             .replace("Failure_Reasons", "Notes")
            for c in display_df.columns
        ]

        def color_status(val):
            if val == "Pass":
                return "color: #16a34a; font-weight: bold"
            elif val == "Fail":
                return "color: #dc2626; font-weight: bold"
            return ""

        styled = display_df.style.applymap(color_status, subset=["Status"] if "Status" in display_df.columns else [])
        st.dataframe(styled, use_container_width=True, hide_index=True)

        # Show table image
        if table_path and os.path.exists(table_path):
            with st.expander("View Compliance Table Image"):
                st.image(table_path, use_container_width=True)

    # --- Time-Series Plots ---
    st.header("4. Time-Series Plots")
    if graph_paths:
        tabs = st.tabs([name.replace("Avg_", "").replace("_", " ") for name in graph_paths.keys()])
        for tab, (name, path) in zip(tabs, graph_paths.items()):
            with tab:
                st.image(path, use_container_width=True)
    else:
        st.info("No plots generated.")

    # --- Event Snapshots ---
    st.header("5. Event Snapshots")
    if snapshot_paths:
        for i, path in enumerate(snapshot_paths, 1):
            with st.expander(f"Event {i}", expanded=(i == 1)):
                st.image(path, use_container_width=True)
    else:
        st.info("No event snapshots generated.")

    # --- Report Generation ---
    st.header("6. Generate Report")

    rcol1, rcol2 = st.columns(2)
    with rcol1:
        template_file = st.file_uploader(
            "Upload Word Template (.docx)",
            type=["docx"],
            help="Upload a .docx file with placeholders like {{Avg_Voltage_LL}}, {{Compliance_Table}}, etc.",
        )
    with rcol2:
        report_filename = st.text_input("Report Filename", value=report_title or "PQA_Report")

        # Show available tags
        with st.expander("Available Placeholders"):
            st.markdown("""
**Graph placeholders:** `{{Avg_Voltage_LL}}`, `{{Avg_kW}}`, `{{Avg_Current}}`, `{{Avg_Frequency}}`, `{{Avg_THD_F}}`, `{{Avg_PF}}`

**Table:** `{{Compliance_Table}}`

**Snapshots:** `{{Snapshot_1}}`, `{{Snapshot_2}}`, ...

**Text fields:** `{{Report_Title}}`, `{{Gen_SN}}`, `{{Site_Address}}`, `{{Custom_Field}}`, `{{Date}}`, `{{Start Time}}`, `{{End Time}}`
            """)

    if template_file is not None:
        if st.button("Generate PQA Report", type="primary"):
            with st.spinner("Generating report..."):
                # Save template temporarily
                os.makedirs(TEMPLATE_DIR, exist_ok=True)
                template_path = os.path.join(TEMPLATE_DIR, template_file.name)
                with open(template_path, "wb") as f:
                    f.write(template_file.read())

                # Build placeholder map
                config_values = {
                    "report_title": report_title,
                    "gen_sn": gen_sn,
                    "site_address": site_address,
                    "custom_text": custom_text,
                }
                df_raw = st.session_state.get("df_raw")
                p_map = get_placeholder_map(
                    client_name, config_values, df=df_raw,
                    graph_dir=GRAPH_DIR, snapshot_dir=SNAPSHOT_DIR, image_dir=IMAGE_DIR,
                )

                # Generate report
                output_base = os.path.join(OUTPUT_BASE, report_filename)
                result = generate_report(template_path, p_map, output_name=output_base)

                # Offer downloads
                st.success("Report generated successfully!")

                dcol1, dcol2 = st.columns(2)
                with dcol1:
                    with open(result["docx"], "rb") as f:
                        st.download_button(
                            "Download Word Report (.docx)",
                            data=f.read(),
                            file_name=f"{report_filename}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True,
                        )
                if "pdf" in result:
                    with dcol2:
                        with open(result["pdf"], "rb") as f:
                            st.download_button(
                                "Download PDF Report",
                                data=f.read(),
                                file_name=f"{report_filename}.pdf",
                                mime="application/pdf",
                                use_container_width=True,
                            )

    # --- Download All as ZIP ---
    st.divider()
    if st.button("Download All Results as ZIP"):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for folder in [GRAPH_DIR, SNAPSHOT_DIR, IMAGE_DIR]:
                if os.path.exists(folder):
                    for root, _, files_list in os.walk(folder):
                        for file in files_list:
                            full_path = os.path.join(root, file)
                            arcname = os.path.relpath(full_path, OUTPUT_BASE)
                            zipf.write(full_path, arcname=arcname)
        zip_buffer.seek(0)
        st.download_button(
            "Save ZIP File",
            data=zip_buffer.getvalue(),
            file_name="PQA_Analysis_Results.zip",
            mime="application/zip",
            use_container_width=True,
        )

else:
    # No analysis run yet - show instructions
    if csv_file is None:
        st.info("Upload a CSV file to get started.")
