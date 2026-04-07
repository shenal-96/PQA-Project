"""
Report generation for Power Quality Analysis.

Handles Word template injection, placeholder mapping, and PDF conversion.
"""

import os
import glob
import subprocess
import io
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH


def get_placeholder_map(client_name, config_values, df=None,
                        graph_dir="output/Graphs",
                        snapshot_dir="output/Snapshots",
                        image_dir="output/Images"):
    """
    Build a mapping of {{placeholder}} -> file path or text value.

    Parameters:
        client_name: string identifier for the client/report
        config_values: dict with keys like 'report_title', 'gen_sn', 'site_address', 'custom_text'
        df: optional DataFrame with Timestamp column for date/time extraction
        graph_dir, snapshot_dir, image_dir: output directories
    """
    placeholder_map = {}

    # Compliance table
    table_path = os.path.join(image_dir, f"{client_name}_table.jpg")
    if os.path.exists(table_path):
        placeholder_map["{{Compliance_Table}}"] = table_path

    # Metric graphs
    metrics = {
        "Avg_Voltage_LL": "{{Avg_Voltage_LL}}",
        "Avg_kW": "{{Avg_kW}}",
        "Avg_Current": "{{Avg_Current}}",
        "Avg_Frequency": "{{Avg_Frequency}}",
        "Avg_THD_F": "{{Avg_THD_F}}",
        "Avg_PF": "{{Avg_PF}}",
    }
    for metric, placeholder in metrics.items():
        graph_path = os.path.join(graph_dir, f"{client_name}_{metric}.jpeg")
        if os.path.exists(graph_path):
            placeholder_map[placeholder] = graph_path

    # Snapshots
    snapshot_files = sorted(glob.glob(os.path.join(snapshot_dir, f"snap_{client_name}_*.jpeg")))
    for i, file_path in enumerate(snapshot_files, start=1):
        placeholder_map[f"{{{{Snapshot_{i}}}}}"] = file_path

    # Text fields
    placeholder_map["{{Report_Title}}"] = config_values.get("report_title", "")
    placeholder_map["{{Gen_SN}}"] = config_values.get("gen_sn", "")
    placeholder_map["{{Site_Address}}"] = config_values.get("site_address", "")
    placeholder_map["{{Custom_Field}}"] = config_values.get("custom_text", "")

    # Date/time from data
    if df is not None and not df.empty and "Timestamp" in df.columns:
        min_ts = df["Timestamp"].min()
        max_ts = df["Timestamp"].max()
        fmt_dt = "%d/%m/%Y %I:%M:%S %p"
        placeholder_map["{{Start Time}}"] = min_ts.strftime(fmt_dt)
        placeholder_map["{{End Time}}"] = max_ts.strftime(fmt_dt)
        placeholder_map["{{Date}}"] = min_ts.strftime("%d/%m/%Y")

    return placeholder_map


def inject_images_to_word(template_stream, placeholder_map):
    """
    Replace {{placeholders}} in a Word document with images or text.

    Parameters:
        template_stream: file path string or file-like BytesIO object
        placeholder_map: dict of {{key}} -> file path or text value

    Returns:
        Document object with replacements applied
    """
    doc = Document(template_stream)

    def apply_strict_formatting(paragraph):
        p_format = paragraph.paragraph_format
        p_format.line_spacing = 1.0
        p_format.space_before = Pt(0)
        p_format.space_after = Pt(0)
        p_format.keep_with_next = True

    def process_paragraphs(paragraphs):
        for paragraph in paragraphs:
            for key, value in placeholder_map.items():
                if key not in paragraph.text:
                    continue
                if isinstance(value, str) and value.lower().endswith((".png", ".jpg", ".jpeg")) and os.path.exists(value):
                    paragraph.text = ""
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    apply_strict_formatting(paragraph)
                    run = paragraph.add_run()
                    run.add_picture(value, width=Inches(6.5))
                else:
                    new_text = paragraph.text.replace(key, str(value))
                    paragraph.text = ""
                    run = paragraph.add_run(new_text)
                    run.font.name = "Arial"
                    run.font.size = Pt(12)

    process_paragraphs(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                process_paragraphs(cell.paragraphs)

    return doc


def generate_report(template_path, placeholder_map, output_name="PQA_Report"):
    """
    Full pipeline: inject placeholders into Word template and optionally convert to PDF.

    Parameters:
        template_path: path to the .docx template
        placeholder_map: dict of {{key}} -> value
        output_name: base filename (without extension) for output files

    Returns:
        dict with 'docx' and optionally 'pdf' keys pointing to file paths
    """
    docx_path = f"{output_name}.docx"

    with open(template_path, "rb") as f:
        doc = inject_images_to_word(io.BytesIO(f.read()), placeholder_map)
    doc.save(docx_path)

    result = {"docx": docx_path}

    # Try PDF conversion via LibreOffice (if available)
    pdf_path = f"{output_name}.pdf"
    try:
        subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf", docx_path],
            check=True, capture_output=True, timeout=60,
        )
        if os.path.exists(pdf_path):
            result["pdf"] = pdf_path
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass  # PDF conversion is optional

    return result
