"""
Report generation for Power Quality Analysis.

Handles Word template injection, placeholder mapping, and PDF conversion.
"""

import os
import glob
import io
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH


_PDF_SCRIPT = """
import sys, os
docx_path, pdf_path = sys.argv[1], sys.argv[2]
try:
    import mammoth
    with open(docx_path, 'rb') as f:
        result = mammoth.convert_to_html(f)
    html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<style>'
        'body{font-family:Arial,sans-serif;font-size:11pt;margin:2cm;line-height:1.4}'
        'img{max-width:100%;height:auto;display:block;margin:10pt auto}'
        'table{width:100%;border-collapse:collapse;margin:10pt 0}'
        'td,th{border:1px solid #ccc;padding:4pt 6pt}'
        'p{margin:4pt 0}'
        '</style></head><body>' + result.value + '</body></html>'
    )
    import weasyprint
    weasyprint.HTML(string=html).write_pdf(pdf_path)
    sys.exit(0)
except ImportError:
    # weasyprint not available, try docx2pdf (Word)
    try:
        from docx2pdf import convert
        convert(docx_path, pdf_path)
        sys.exit(0)
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(e, file=sys.stderr)
    sys.exit(1)
"""


def convert_to_pdf(docx_path, pdf_path, timeout=45):
    """
    Run PDF conversion in a subprocess with a timeout.
    Returns True if a PDF was produced within the time limit.
    """
    import sys
    import subprocess

    try:
        subprocess.run(
            [sys.executable, "-c", _PDF_SCRIPT,
             os.path.abspath(docx_path), os.path.abspath(pdf_path)],
            timeout=timeout,
            capture_output=True,
        )
        return os.path.exists(pdf_path)
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


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


def generate_docx(template_path, placeholder_map, output_name="PQA_Report"):
    """
    Inject placeholders into a Word template and save the .docx.
    Returns the path to the saved .docx file.
    """
    docx_path = f"{output_name}.docx"
    with open(template_path, "rb") as f:
        doc = inject_images_to_word(io.BytesIO(f.read()), placeholder_map)
    doc.save(docx_path)
    return docx_path


def generate_report(template_path, placeholder_map, output_name="PQA_Report"):
    """
    Full pipeline: inject placeholders into Word template and optionally convert to PDF.
    Returns dict with 'docx' and optionally 'pdf' keys pointing to file paths.
    """
    docx_path = generate_docx(template_path, placeholder_map, output_name)
    result = {"docx": docx_path}
    pdf_path = f"{output_name}.pdf"
    if convert_to_pdf(docx_path, pdf_path):
        result["pdf"] = pdf_path
    return result
