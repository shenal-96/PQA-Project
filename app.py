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
</style>
""", unsafe_allow_html=True)


def _get_csv_time_range(uploaded_file):
    """Read a CSV and return (start_str, end_str) or (None, None)."""
    try:
        pos = uploaded_file.tell()
        uploaded_file.seek(0)
        temp_df = load_and_prepare_csv(uploaded_file)
        uploaded_file.seek(pos)
        if not temp_df.empty:
            return (
                temp_df["Timestamp"].min().strftime("%H:%M:%S"),
                temp_df["Timestamp"].max().strftime("%H:%M:%S"),
            )
    except Exception:
        pass
    return (None, None)


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.title("\u2699\ufe0f Configuration")

    # ── 1. CSV Upload ──────────────────────────────────────────
    st.subheader("Data Files")
    csv_files = st.file_uploader(
        "Upload CSV files",
        type=["csv"],
        accept_multiple_files=True,
        help="Upload one or more CSV files from your power quality recorder.",
    )

    selected_csv = None
    client_name = ""
    auto_start = ""
    auto_end = ""

    if csv_files:
        selected_name = st.selectbox("Select CSV to analyse", [f.name for f in csv_files])
        selected_csv = next(f for f in csv_files if f.name == selected_name)
        client_name = os.path.splitext(selected_csv.name)[0]
        auto_start, auto_end = _get_csv_time_range(selected_csv)
        selected_csv.seek(0)

    st.divider()

    # ── 2. Acceptance Criteria ────────────────────────────────
    st.subheader("Acceptance Criteria")
    apply_iso = st.checkbox("Apply ISO 8528 Presets", value=False)

    if apply_iso:
        load_thresh = 50.0; v_tol = 1.0; v_rec = 4.0; v_max_dev = 15.0
        f_tol = 0.5; f_rec = 3.0; f_max_dev = 7.0
        st.info("ISO 8528 presets applied")
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

    # ── 3. Display Options ────────────────────────────────────
    st.subheader("Display Options")
    show_limits = st.checkbox("Show Limits on Graphs", value=False)
    nom_v = st.number_input("Nominal Voltage (V)", value=415.0, step=1.0)
    nom_f = st.number_input("Nominal Frequency (Hz)", value=50.0, step=0.5)

    st.divider()

    # ── 4. Time Filter ────────────────────────────────────────
    st.subheader("Time Filter")
    start_time = st.text_input("Start Time", value=auto_start or "", placeholder="HH:MM:SS")
    end_time = st.text_input("End Time", value=auto_end or "", placeholder="HH:MM:SS")

    st.divider()

    # ── 5. Run Analysis ───────────────────────────────────────
    run_clicked = False
    if selected_csv is not None:
        run_clicked = st.button("\u26a1 Run Analysis", type="primary", width="stretch")
    else:
        st.info("Upload CSV files above to begin.")

    st.divider()

    # ── 6. Report Details ─────────────────────────────────────
    st.subheader("Report Details")
    report_title = st.text_input("Report Title", value=client_name, placeholder="Enter report/client name")
    gen_sn = st.text_input("Generator Serial Number", placeholder="Enter Gen S/N")
    site_address = st.text_input("Site Address", placeholder="Enter site address")
    custom_text = st.text_input("Custom Text Field", placeholder="Enter custom info")

    st.divider()

    # ── 7. Report Generation ──────────────────────────────────
    st.subheader("Generate Report")

    template_files = st.file_uploader(
        "Upload Word Templates (.docx)",
        type=["docx"],
        accept_multiple_files=True,
        help="Upload one or more .docx templates with placeholders.",
    )

    selected_template = None
    if template_files:
        template_names = [f.name for f in template_files]
        selected_template_name = st.selectbox("Select Template", template_names)
        selected_template = next(f for f in template_files if f.name == selected_template_name)

        with st.expander("Available Placeholders"):
            st.markdown("""
`{{Avg_Voltage_LL}}` `{{Avg_kW}}` `{{Avg_Current}}`
`{{Avg_Frequency}}` `{{Avg_THD_F}}` `{{Avg_PF}}`
`{{Compliance_Table}}`
`{{Snapshot_1}}` `{{Snapshot_2}}` ...
`{{Report_Title}}` `{{Gen_SN}}` `{{Site_Address}}`
`{{Custom_Field}}` `{{Date}}` `{{Start Time}}` `{{End Time}}`
            """)

    report_filename = st.text_input(
        "Report Filename",
        value=client_name or "PQA_Report",
        placeholder="Enter filename (no extension)",
    )

    with st.expander("⬇️ Download Options"):
        download_format = st.selectbox(
            "Download Format",
            ["Word (.docx)", "PDF", "Both"],
        )

    generate_clicked = False
    if selected_template is not None and st.session_state.get("analysis_done"):
        generate_clicked = st.button("\U0001f4c4 Generate Report", type="primary", width="stretch")
    elif not st.session_state.get("analysis_done"):
        st.caption("Run analysis first to enable report generation.")
    else:
        st.caption("Upload a template above to generate a report.")


# ============================================================
# MAIN AREA
# ============================================================
st.title("\u26a1 Power Quality Analysis")

if selected_csv is not None:
    with st.expander("Preview uploaded data", expanded=False):
        selected_csv.seek(0)
        preview_df = pd.read_csv(selected_csv, sep=None, engine="python", nrows=10)
        st.dataframe(preview_df, width="stretch")
        selected_csv.seek(0)

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
        )

        with st.spinner("Loading and processing data..."):
            selected_csv.seek(0)
            df_raw = load_and_prepare_csv(selected_csv, start_time=start_time, end_time=end_time)
            selected_csv.seek(0)
            if df_raw.empty:
                st.error("No data found. Check your CSV and time range.")
                st.stop()
            df_proc, df_events = perform_analysis(df_raw, config)

        st.session_state.update({
            "df_raw": df_raw,
            "df_proc": df_proc,
            "df_events": df_events,
            "client_name": client_name,
            "config": config,
            "analysis_done": True,
            "generated_reports": st.session_state.get("generated_reports", []),
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

        with st.spinner("Generating plots..."):
            graph_paths = generate_plots(
                df_proc, client_name, output_dir=GRAPH_DIR,
                show_limits=show_limits, nom_v=nom_v, nom_f=nom_f,
                tol_v=v_tol, tol_f=f_tol,
            )
        st.session_state["graph_paths"] = graph_paths

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
        disp = df_events[
            [c for c in ["Timestamp","dKw","V_dev","F_dev","V_rec_s","F_rec_s","Compliance_Status","Failure_Reasons"]
             if c in df_events.columns]
        ].copy()
        if "Timestamp" in disp.columns:
            disp["Timestamp"] = disp["Timestamp"].dt.strftime("%H:%M:%S")
        if "dKw" in disp.columns: disp["dKw"] = disp["dKw"].round(1)
        if "V_dev" in disp.columns: disp["V_dev"] = (disp["V_dev"] / config.nominal_voltage * 100).round(1)
        if "F_dev" in disp.columns: disp["F_dev"] = (disp["F_dev"] / config.nominal_frequency * 100).round(1)
        if "V_rec_s" in disp.columns: disp["V_rec_s"] = disp["V_rec_s"].round(1)
        if "F_rec_s" in disp.columns: disp["F_rec_s"] = disp["F_rec_s"].round(1)
        disp.columns = [
            c.replace("dKw","Load Change (kW)").replace("V_dev","V Dev (%)").replace("F_dev","F Dev (%)")
             .replace("V_rec_s","V Recovery (s)").replace("F_rec_s","F Recovery (s)")
             .replace("Compliance_Status","Status").replace("Failure_Reasons","Notes")
            for c in disp.columns
        ]

        def color_status(val):
            if val == "Pass": return "color: #16a34a; font-weight: bold"
            elif val == "Fail": return "color: #dc2626; font-weight: bold"
            return ""

        st.dataframe(
            disp.style.map(color_status, subset=["Status"] if "Status" in disp.columns else []),
            width="stretch", hide_index=True,
        )
        if table_path and os.path.exists(table_path):
            with st.expander("View Compliance Table Image"):
                st.image(table_path, width="stretch")

    # Time-Series Plots
    st.header("Time-Series Plots")
    if graph_paths:
        tabs = st.tabs([n.replace("Avg_", "").replace("_", " ") for n in graph_paths.keys()])
        for tab, (name, path) in zip(tabs, graph_paths.items()):
            with tab:
                st.image(path, width="stretch")
    else:
        st.info("No plots generated.")

    # Event Snapshots
    st.header("Event Snapshots")
    if snapshot_paths:
        for i, path in enumerate(snapshot_paths, 1):
            with st.expander(f"Event {i}", expanded=(i == 1)):
                st.image(path, width="stretch")
    else:
        st.info("No event snapshots generated.")

    # ── Report Generation ─────────────────────────────────────
    if generate_clicked and selected_template is not None:
        with st.spinner("Generating report..."):
            os.makedirs(TEMPLATE_DIR, exist_ok=True)
            template_path = os.path.join(TEMPLATE_DIR, selected_template.name)
            selected_template.seek(0)
            with open(template_path, "wb") as f:
                f.write(selected_template.read())

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
            output_base = os.path.join(OUTPUT_BASE, report_filename)
            result = generate_report(template_path, p_map, output_name=output_base)

            # Read generated file bytes into memory for download
            entry = {"name": report_filename, "format": download_format, "files": {}}
            with open(result["docx"], "rb") as f:
                entry["files"]["docx"] = f.read()
            if "pdf" in result:
                with open(result["pdf"], "rb") as f:
                    entry["files"]["pdf"] = f.read()

            reports = st.session_state.get("generated_reports", [])
            reports.append(entry)
            st.session_state["generated_reports"] = reports
            st.success(f"Report '{report_filename}' generated.")

    # ── Generated Reports List ────────────────────────────────
    reports = st.session_state.get("generated_reports", [])
    if reports:
        st.header("Generated Reports")

        # Display as a clean table
        table_rows = []
        for entry in reports:
            fmt = entry["format"]
            files_available = []
            if "docx" in entry["files"] and fmt in ("Word (.docx)", "Both"):
                files_available.append("Word (.docx)")
            if "pdf" in entry["files"] and fmt in ("PDF", "Both"):
                files_available.append("PDF")
            elif fmt in ("PDF", "Both") and "pdf" not in entry["files"]:
                files_available.append("PDF (unavailable — LibreOffice not installed)")
            table_rows.append({
                "Report Name": entry["name"],
                "Format": fmt,
                "Files": ", ".join(files_available) if files_available else "—",
            })

        st.dataframe(
            pd.DataFrame(table_rows),
            hide_index=True,
            width="stretch",
        )

        # Build a zip of all generated reports and offer single download
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for entry in reports:
                fmt = entry["format"]
                if "docx" in entry["files"] and fmt in ("Word (.docx)", "Both"):
                    zipf.writestr(f"{entry['name']}.docx", bytes(entry["files"]["docx"]))
                if "pdf" in entry["files"] and fmt in ("PDF", "Both"):
                    zipf.writestr(f"{entry['name']}.pdf", bytes(entry["files"]["pdf"]))
        zip_data = zip_buffer.getvalue()

        st.download_button(
            label="⬇️ Download Reports",
            data=zip_data,
            file_name="PQA_Reports.zip",
            mime="application/zip",
        )

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
