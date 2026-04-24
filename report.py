"""
Report generation for Power Quality Analysis.

Handles Word template injection, placeholder mapping, and PDF conversion.
"""

import os
import glob
import io
import logging
import pandas as pd
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

log = logging.getLogger(__name__)


_PDF_SCRIPT = r"""
import sys, os, io, tempfile
docx_path, pdf_path = sys.argv[1], sys.argv[2]

def try_libreoffice():
    import shutil as _shutil
    import subprocess as _sp

    candidates = [
        'libreoffice',
        'soffice',
        '/Applications/LibreOffice.app/Contents/MacOS/soffice',
        '/usr/bin/libreoffice',
        '/usr/bin/soffice',
        '/snap/bin/libreoffice',
        'C:\\Program Files\\LibreOffice\\program\\soffice.exe',
        'C:\\Program Files (x86)\\LibreOffice\\program\\soffice.exe',
    ]
    lo_bin = None
    for c in candidates:
        try:
            r = _sp.run([c, '--version'], capture_output=True, timeout=5)
            if r.returncode == 0:
                lo_bin = c
                break
        except Exception:
            continue
    if not lo_bin:
        raise RuntimeError('LibreOffice not found')

    out_dir = os.path.dirname(os.path.abspath(pdf_path))
    _sp.run(
        [lo_bin, '--headless', '--convert-to', 'pdf', '--outdir', out_dir,
         os.path.abspath(docx_path)],
        check=True, capture_output=True, timeout=90,
    )
    # LibreOffice names the output after the input basename
    expected = os.path.join(out_dir, os.path.splitext(os.path.basename(docx_path))[0] + '.pdf')
    if os.path.exists(expected) and os.path.abspath(expected) != os.path.abspath(pdf_path):
        _shutil.move(expected, pdf_path)

def try_docx2pdf():
    from docx2pdf import convert
    convert(docx_path, pdf_path)
    if not os.path.exists(pdf_path):
        raise RuntimeError('docx2pdf ran but no output file produced')

def try_weasyprint():
    import mammoth, weasyprint
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
    weasyprint.HTML(string=html).write_pdf(pdf_path)

def try_fpdf2():
    from docx import Document
    from docx.oxml.ns import qn
    from fpdf import FPDF
    from PIL import Image

    doc = Document(docx_path)
    pdf = FPDF(format='A4')
    pdf.set_margins(20, 20, 20)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)

    # Extract embedded images from the docx zip
    import zipfile
    img_map = {}
    with zipfile.ZipFile(docx_path) as z:
        for name in z.namelist():
            if name.startswith('word/media/'):
                ext = os.path.splitext(name)[1].lower()
                if ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp'):
                    img_map[name] = z.read(name)

    # Map relationship IDs to image data
    rel_to_img = {}
    with zipfile.ZipFile(docx_path) as z:
        if 'word/_rels/document.xml.rels' in z.namelist():
            import xml.etree.ElementTree as ET
            rels_xml = z.read('word/_rels/document.xml.rels')
            root = ET.fromstring(rels_xml)
            for rel in root:
                target = rel.get('Target', '')
                if 'media/' in target:
                    rid = rel.get('Id')
                    img_key = 'word/' + target.lstrip('/')
                    if img_key in img_map:
                        rel_to_img[rid] = img_map[img_key]

    tmp_imgs = []
    page_w = pdf.w - pdf.l_margin - pdf.r_margin

    for para in doc.paragraphs:
        # Check for inline images
        for elem in para._element.iter():
            if elem.tag.endswith('}blip'):
                rid = elem.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                if rid and rid in rel_to_img:
                    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                    tmp.write(rel_to_img[rid])
                    tmp.close()
                    tmp_imgs.append(tmp.name)
                    try:
                        with Image.open(tmp.name) as im:
                            w, h = im.size
                        ratio = h / w if w > 0 else 1
                        img_w = min(page_w, page_w)
                        img_h = img_w * ratio
                        if pdf.get_y() + img_h > pdf.page_break_trigger:
                            pdf.add_page()
                        pdf.image(tmp.name, x=pdf.l_margin, w=img_w)
                        pdf.ln(3)
                    except Exception:
                        pass

        text = para.text.strip()
        if not text:
            pdf.ln(3)
            continue

        style = para.style.name if para.style else ''
        if 'Heading 1' in style:
            pdf.set_font('Helvetica', 'B', 16)
        elif 'Heading 2' in style:
            pdf.set_font('Helvetica', 'B', 13)
        elif 'Heading' in style:
            pdf.set_font('Helvetica', 'B', 11)
        else:
            pdf.set_font('Helvetica', '', 11)

        pdf.multi_cell(0, 6, text)
        pdf.ln(1)

    pdf.output(pdf_path)

    for t in tmp_imgs:
        try: os.unlink(t)
        except: pass

# Try converters in order
for converter in [try_libreoffice, try_docx2pdf, try_weasyprint, try_fpdf2]:
    try:
        converter()
        if os.path.exists(pdf_path):
            print(f'PDF conversion succeeded via {converter.__name__}')
            sys.exit(0)
    except Exception as e:
        print(f'{converter.__name__} failed: {e}', file=sys.stderr)

sys.exit(1)
"""


def convert_to_pdf(docx_path, pdf_path, timeout=45):
    """
    Run PDF conversion in a subprocess with a timeout.
    Returns (success: bool, log: str) — log contains converter diagnostics
    whether conversion succeeded or failed.
    """
    import sys
    import subprocess

    try:
        result = subprocess.run(
            [sys.executable, "-c", _PDF_SCRIPT,
             os.path.abspath(docx_path), os.path.abspath(pdf_path)],
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        success = os.path.exists(pdf_path)
        log_lines = []
        if result.stdout.strip():
            log_lines.append(result.stdout.strip())
        if result.stderr.strip():
            log_lines.append(result.stderr.strip())
        if not log_lines:
            log_lines.append("(no output from converter)")
        log = "\n".join(log_lines)
        return success, log
    except subprocess.TimeoutExpired:
        return False, f"Timed out after {timeout}s — converter hung."
    except Exception as e:
        return False, f"Subprocess error: {e}"


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
    table_path = os.path.join(image_dir, f"{client_name}_table.png")
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
    placeholder_map["{{PQID}}"] = config_values.get("pqa_serial", "")
    placeholder_map["{{Gen_SN}}"] = config_values.get("gen_sn", "")
    placeholder_map["{{Site_Address}}"] = config_values.get("site_address", "")
    placeholder_map["{{Custom_Field}}"] = config_values.get("custom_text", "")

    # Date/time extracted from CSV data (not today's date)
    if df is not None and not df.empty and "Timestamp" in df.columns:
        min_ts = df["Timestamp"].min()
        max_ts = df["Timestamp"].max()
        fmt_dt = "%d/%m/%Y %I:%M:%S %p"
        placeholder_map["{{Start Time}}"] = min_ts.strftime(fmt_dt)
        placeholder_map["{{End Time}}"] = max_ts.strftime(fmt_dt)

        # Extract {{Date}} directly from the CSV "Date" column when available.
        # This avoids inheriting wrong dates from a "PC Time" column that may
        # have a misconfigured clock. Fallback is Timestamp.min() (also CSV-
        # sourced). No fallback to the computer's current date in either path.
        date_str = None
        if "Date" in df.columns:
            raw_date = df["Date"].dropna()
            if not raw_date.empty:
                try:
                    parsed = pd.to_datetime(raw_date.iloc[0], dayfirst=True)
                    date_str = parsed.strftime("%d/%m/%Y")
                except Exception:
                    pass
        if date_str is None:
            date_str = min_ts.strftime("%d/%m/%Y")
        placeholder_map["{{Date}}"] = date_str

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

    # Derive usable content width from the first section's page geometry.
    # A small safety buffer (0.15 in) is subtracted so images never reach the
    # exact margin edge — LibreOffice's PDF renderer can introduce sub-mm
    # offsets that clip a full-width image on the right side.
    try:
        _sec = doc.sections[0]
        _content_width = _sec.page_width - _sec.left_margin - _sec.right_margin - Inches(0.15)
    except Exception:
        _content_width = Inches(6.35)  # safe fallback

    def apply_strict_formatting(paragraph):
        p_format = paragraph.paragraph_format
        p_format.line_spacing = 1.0
        p_format.space_before = Pt(0)
        p_format.space_after = Pt(0)
        p_format.keep_with_next = False
        p_format.left_indent = Inches(0)
        p_format.right_indent = Inches(0)
        p_format.first_line_indent = Inches(0)
        # Also clear the indent at the XML level so style-inherited indents
        # don't survive into LibreOffice's PDF renderer.
        pPr = paragraph._p.get_or_add_pPr()
        ind = pPr.find(qn("w:ind"))
        if ind is not None:
            pPr.remove(ind)
        ind_elem = OxmlElement("w:ind")
        ind_elem.set(qn("w:left"), "0")
        ind_elem.set(qn("w:right"), "0")
        ind_elem.set(qn("w:firstLine"), "0")
        pPr.append(ind_elem)

    def _collapse_trailing_empties(para_elem, max_keep=1):
        """
        Remove consecutive empty paragraphs that immediately follow para_elem,
        keeping at most max_keep of them.  Templates often use long runs of empty
        paragraphs for spacing; after an image is injected those lines overflow
        onto the next page and produce a blank page.
        """
        body = para_elem.getparent()
        if body is None:
            return
        children = list(body)
        try:
            start = children.index(para_elem) + 1
        except ValueError:
            return
        empties = []
        for child in children[start:]:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag != "p":
                break
            text = "".join(t.text or "" for t in child.findall(".//" + qn("w:t"))).strip()
            if text:
                break
            empties.append(child)
        for elem in empties[max_keep:]:
            body.remove(elem)

    def preserve_paragraph_spacing(paragraph):
        """Ensure paragraphs have explicit spacing for LibreOffice PDF conversion."""
        p_format = paragraph.paragraph_format
        # Only set if not already set (preserve template intent)
        if p_format.space_before is None or p_format.space_before == Pt(0):
            p_format.space_before = Pt(3)
        if p_format.space_after is None or p_format.space_after == Pt(0):
            p_format.space_after = Pt(3)

    def process_paragraphs(paragraphs):
        for paragraph in paragraphs:
            # Build full paragraph text from all runs (handles split placeholders)
            full_text = "".join([run.text for run in paragraph.runs])
            new_text = full_text
            has_image = False
            image_path = None

            for key, value in placeholder_map.items():
                if key not in new_text:
                    continue

                if isinstance(value, str) and value.lower().endswith((".png", ".jpg", ".jpeg")) and os.path.exists(value):
                    # Image replacement: mark for processing after text replacements
                    has_image = True
                    image_path = value
                else:
                    # Text replacement: apply to new_text (which accumulates all replacements)
                    new_text = new_text.replace(key, str(value))

            # Now apply the accumulated changes to the paragraph
            if has_image and image_path:
                # Image replacement: clear paragraph and add image
                for run in paragraph.runs:
                    run._element.getparent().remove(run._element)
                paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                apply_strict_formatting(paragraph)
                run = paragraph.add_run()
                run.add_picture(image_path, width=_content_width)
                _collapse_trailing_empties(paragraph._p)
            elif new_text != full_text:
                # Text replacements were made: clear runs and rebuild once
                for run in list(paragraph.runs):
                    run._element.getparent().remove(run._element)

                # Add new run with replaced text, preserving font
                run = paragraph.add_run(new_text)
                run.font.name = "Arial"
                run.font.size = Pt(11)  # Use 11pt for body text, not 12pt

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
