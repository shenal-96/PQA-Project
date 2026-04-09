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

from analysis import AnalysisConfig, load_and_prepare_csv, perform_analysis
from visualizations import (
    generate_plots,
    generate_all_snapshots,
    save_compliance_table_as_image,
)
from report import get_placeholder_map, inject_images_to_word, generate_docx, convert_to_pdf

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

# --- Persistent upload directories ---
UPLOADS_CSV_DIR = "uploads/csv"
UPLOADS_TEMPLATE_DIR = "uploads/templates"
os.makedirs(UPLOADS_CSV_DIR, exist_ok=True)
os.makedirs(UPLOADS_TEMPLATE_DIR, exist_ok=True)


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


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.title("\u2699\ufe0f Configuration")

    # ── 1. CSV Upload ──────────────────────────────────────────
    st.subheader("Data Files")
    new_csvs = st.file_uploader(
        "Upload CSV files",
        type=["csv"],
        accept_multiple_files=True,
        help="Files are saved locally — no need to re-upload each session.",
    )
    if new_csvs:
        for f in new_csvs:
            dest = os.path.join(UPLOADS_CSV_DIR, f.name)
            f.seek(0)
            with open(dest, "wb") as out:
                out.write(f.read())
        st.rerun()

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
        selected_name = st.selectbox("Select CSV to analyse", all_csv_names)
        selected_csv_path = os.path.join(UPLOADS_CSV_DIR, selected_name)
        client_name = os.path.splitext(selected_name)[0]
        auto_start, auto_end = _get_csv_time_range(selected_csv_path)

    st.divider()

    # ── 2. Acceptance Criteria ────────────────────────────────
    st.subheader("Acceptance Criteria")
    apply_iso = st.checkbox("Apply ISO 8528 Presets", value=False)

    if apply_iso:
        load_thresh = 50.0; v_tol = 1.0; v_rec = 4.0; v_max_dev = 15.0
        f_tol = 0.5; f_rec = 3.0; f_max_dev = 7.0
        st.info("ISO 8528 presets applied")
        st.markdown(f"""
| Parameter | Value |
|---|---|
| Load Threshold | {load_thresh} kW |
| V Tolerance | {v_tol}% |
| V Recovery | {v_rec} s |
| V Max Dev | {v_max_dev}% |
| F Tolerance | {f_tol}% |
| F Recovery | {f_rec} s |
| F Max Dev | {f_max_dev}% |
""")
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
    start_time_text = st.text_input("Start Time", value=auto_start or "", placeholder="HH:MM:SS")
    end_time_text = st.text_input("End Time", value=auto_end or "", placeholder="HH:MM:SS")

    start_time = start_time_text
    end_time = end_time_text

    if auto_start and auto_end:
        try:
            def _parse_time(s):
                parts = [int(x) for x in s.split(":")]
                return datetime.time(*parts)

            t_min = _parse_time(auto_start)
            t_max = _parse_time(auto_end)

            try: t_start_val = _parse_time(start_time_text) if start_time_text else t_min
            except: t_start_val = t_min
            try: t_end_val = _parse_time(end_time_text) if end_time_text else t_max
            except: t_end_val = t_max

            t_start_val = max(t_min, min(t_max, t_start_val))
            t_end_val = max(t_min, min(t_max, t_end_val))

            start_slider = st.slider(
                "Start", min_value=t_min, max_value=t_max, value=t_start_val,
                format="HH:mm:ss", step=datetime.timedelta(seconds=30),
                label_visibility="collapsed",
                key=f"start_slider_{client_name}",
            )
            end_slider = st.slider(
                "End", min_value=t_min, max_value=t_max, value=t_end_val,
                format="HH:mm:ss", step=datetime.timedelta(seconds=30),
                label_visibility="collapsed",
                key=f"end_slider_{client_name}",
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
    gen_sn = st.text_input("Generator Serial Number", placeholder="Enter Gen S/N")
    site_address = st.text_input("Site Address", placeholder="Enter site address")
    custom_text = st.text_input("Custom Text Field", placeholder="Enter custom info")

    st.divider()

    # ── 7. Report Generation ──────────────────────────────────
    st.subheader("Generate Report")

    new_templates = st.file_uploader(
        "Upload Word Templates (.docx)",
        type=["docx"],
        accept_multiple_files=True,
        help="Files are saved locally — no need to re-upload each session.",
    )
    if new_templates:
        for f in new_templates:
            dest = os.path.join(UPLOADS_TEMPLATE_DIR, f.name)
            f.seek(0)
            with open(dest, "wb") as out:
                out.write(f.read())
        st.rerun()

    saved_templates = sorted(glob.glob(os.path.join(UPLOADS_TEMPLATE_DIR, "*.docx")))

    # Show saved templates with size and remove button
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

    selected_template_path = None
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
    if selected_template_path is not None and st.session_state.get("analysis_done"):
        generate_clicked = st.button("\U0001f4c4 Generate Report", type="primary", use_container_width=True)
    elif not st.session_state.get("analysis_done"):
        st.caption("Run analysis first to enable report generation.")
    else:
        st.caption("Upload a template above to generate a report.")

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
            if "pdf" in entry["files"]:
                c2.download_button(
                    "⬇ .pdf",
                    data=bytes(entry["files"]["pdf"]),
                    file_name=f"{entry['name']}.pdf",
                    mime="application/pdf",
                    key=f"sb_dl_pdf_{i}",
                    use_container_width=True,
                )
            elif "docx" in entry["files"]:
                c2.caption("PDF n/a")

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for entry in sidebar_reports:
                if "docx" in entry["files"]:
                    zipf.writestr(f"{entry['name']}.docx", bytes(entry["files"]["docx"]))
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
        )

        with st.spinner("Loading and processing data..."):
            df_raw = load_and_prepare_csv(selected_csv_path, start_time=start_time, end_time=end_time)
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

        plot_kwargs = dict(
            output_dir=GRAPH_DIR, show_limits=show_limits,
            nom_v=nom_v, nom_f=nom_f, tol_v=v_tol, tol_f=f_tol,
        )
        with st.spinner("Generating voltage plot..."):
            graph_paths = generate_plots(df_proc, client_name, metric_keys=["Avg_Voltage_LL"], **plot_kwargs)
        st.session_state["graph_paths"] = graph_paths

        with st.spinner("Generating remaining plots..."):
            other_paths = generate_plots(
                df_proc, client_name,
                metric_keys=["Avg_kW", "Avg_Current", "Avg_Frequency", "Avg_PF", "Avg_THD_F"],
                **plot_kwargs,
            )
            graph_paths.update(other_paths)
        st.session_state["graph_paths"] = graph_paths

        snapshot_paths = []
        table_path = None
        if not df_events.empty:
            with st.spinner("Generating compliance table..."):
                table_file = os.path.join(IMAGE_DIR, f"{client_name}_table.jpg")
                table_path = save_compliance_table_as_image(
                    df_events, table_file,
                    f"Compliance Report: {client_name}",
                    nom_v=nom_v, nom_f=nom_f,
                )
            with st.spinner("Generating event snapshots..."):
                snapshot_paths = generate_all_snapshots(df_raw, df_events, client_name, output_dir=SNAPSHOT_DIR)
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
                st.image(table_path, use_container_width=True)

    # Time-Series Plots
    st.header("Time-Series Plots")
    if graph_paths:
        tabs = st.tabs([n.replace("Avg_", "").replace("_", " ") for n in graph_paths.keys()])
        for tab, (name, path) in zip(tabs, graph_paths.items()):
            with tab:
                st.image(path, use_container_width=True)
    else:
        st.info("No plots generated.")

    # Event Snapshots
    st.header("Event Snapshots")
    if snapshot_paths:
        for i, path in enumerate(snapshot_paths, 1):
            with st.expander(f"Event {i}", expanded=(i == 1)):
                st.image(path, use_container_width=True)
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
if generate_clicked and selected_template_path is not None:
    import traceback as _tb

    client_name_display = st.session_state.get("client_name", client_name)
    _success = False
    _error_tb = None

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

                st.write("📝 Injecting content into Word template...")
                output_base = os.path.join(OUTPUT_BASE, report_filename)
                docx_path = generate_docx(selected_template_path, p_map, output_name=output_base)

                st.write("💾 Word document ready — reading file...")
                entry = {"name": report_filename, "files": {}}
                with open(docx_path, "rb") as f:
                    entry["files"]["docx"] = f.read()

                st.write("🖨️ Converting to PDF (timeout: 45s)...")
                pdf_path = f"{output_base}.pdf"
                if convert_to_pdf(docx_path, pdf_path):
                    with open(pdf_path, "rb") as f:
                        entry["files"]["pdf"] = f.read()
                    st.write("✅ PDF ready.")
                else:
                    st.write("⚠️ PDF conversion unavailable — .docx only.")

                reports = st.session_state.get("generated_reports", [])
                reports.append(entry)
                st.session_state["generated_reports"] = reports

                _status.update(label=f"✅ '{report_filename}' generated!", state="complete", expanded=False)
                _success = True

            except Exception as _exc:
                _error_tb = _tb.format_exc()
                _status.update(label=f"❌ Failed: {_exc}", state="error", expanded=True)
                st.write(str(_exc))

    if _error_tb:
        st.error("Report generation failed — full traceback:")
        st.code(_error_tb, language="python")

    if _success:
        st.rerun()
