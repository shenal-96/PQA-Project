"""
HTML-based report generation for Power Quality Analysis.

Provides an alternative to the Word template pipeline:
  1. A default HTML template with {{placeholders}} matching the Word convention.
  2. Placeholder injection (images embedded as base64, text substituted in-place).
  3. HTML → PDF conversion: WeasyPrint → LibreOffice → reportlab fallback.
  4. Full pipeline function returning {"html": path, "pdf": path | None}.
"""

import base64
import logging
import os
import shutil
import subprocess
import sys
import tempfile

log = logging.getLogger(__name__)


# ── Default HTML template ──────────────────────────────────────────────────

def get_default_template() -> str:
    """
    Return the default PQA report HTML template string.
    Placeholders use {{PLACEHOLDER}} convention, matching the Word template system.
    Image placeholders are replaced with base64-embedded <img> tags at inject time.
    """
    return """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{Report_Title}} — Power Quality Analysis Report</title>
  <style>
    /* ── Reset & base ── */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { font-size: 10pt; }
    body {
      font-family: Arial, Helvetica, sans-serif;
      color: #0f172a;
      background: #ffffff;
      line-height: 1.55;
    }

    /* ── Page layout ── */
    .page {
      max-width: 210mm;
      margin: 0 auto;
      padding: 14mm 16mm 12mm;
    }

    /* ── Header ── */
    .report-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      border-bottom: 3px solid #2563eb;
      padding-bottom: 10px;
      margin-bottom: 20px;
    }
    .report-header .brand {
      font-size: 9pt;
      color: #64748b;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-weight: 700;
    }
    .report-header .brand span {
      display: block;
      font-size: 18pt;
      font-weight: 900;
      color: #0f172a;
      letter-spacing: -0.03em;
      text-transform: none;
      line-height: 1.1;
    }
    .report-header .meta {
      text-align: right;
      font-size: 8.5pt;
      color: #475569;
      line-height: 1.8;
    }
    .report-header .meta strong {
      color: #0f172a;
      font-weight: 700;
    }

    /* ── Section headings ── */
    .section-title {
      font-size: 11pt;
      font-weight: 800;
      color: #1e3a8a;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      border-left: 4px solid #2563eb;
      padding-left: 8px;
      margin: 22px 0 10px;
    }

    /* ── Info grid ── */
    .info-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px 24px;
      background: #f1f5f9;
      border-radius: 6px;
      padding: 12px 16px;
      margin-bottom: 16px;
    }
    .info-row { display: flex; gap: 6px; align-items: baseline; }
    .info-label {
      font-size: 7.5pt;
      font-weight: 700;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      white-space: nowrap;
      min-width: 90px;
    }
    .info-value {
      font-size: 9pt;
      color: #0f172a;
      font-weight: 600;
    }

    /* ── Compliance table image ── */
    .compliance-block {
      margin: 10px 0 20px;
      text-align: center;
    }
    .compliance-block img {
      max-width: 100%;
      height: auto;
      border: 1px solid #e2e8f0;
      border-radius: 4px;
    }

    /* ── Metric chart grid ── */
    .chart-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
      margin: 10px 0 20px;
    }
    .chart-block {
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      overflow: hidden;
      background: #f8fafc;
    }
    .chart-label {
      font-size: 7.5pt;
      font-weight: 700;
      color: #475569;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      padding: 5px 8px 4px;
      background: #f1f5f9;
      border-bottom: 1px solid #e2e8f0;
    }
    .chart-block img {
      width: 100%;
      height: auto;
      display: block;
    }

    /* ── Event snapshots ── */
    .snapshot-block {
      margin: 0 0 18px;
      page-break-inside: avoid;
    }
    .snapshot-block .snapshot-title {
      font-size: 8pt;
      font-weight: 700;
      color: #475569;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 5px;
    }
    .snapshot-block img {
      max-width: 100%;
      height: auto;
      border: 1px solid #e2e8f0;
      border-radius: 4px;
      display: block;
    }

    /* ── Custom notes ── */
    .notes-block {
      background: #fffbeb;
      border: 1px solid #fcd34d;
      border-radius: 6px;
      padding: 10px 14px;
      margin: 16px 0;
      font-size: 9pt;
      color: #92400e;
      line-height: 1.5;
    }
    .notes-block .notes-label {
      font-weight: 700;
      font-size: 7.5pt;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      margin-bottom: 4px;
      color: #78350f;
    }

    /* ── Footer ── */
    .report-footer {
      margin-top: 28px;
      padding-top: 8px;
      border-top: 1px solid #e2e8f0;
      display: flex;
      justify-content: space-between;
      font-size: 7.5pt;
      color: #94a3b8;
    }
  </style>
</head>
<body>
<div class="page">

  <!-- Header -->
  <div class="report-header">
    <div class="brand">
      Power Quality Analysis
      <span>{{Report_Title}}</span>
    </div>
    <div class="meta">
      <strong>Date:</strong> {{Date}}<br>
      <strong>From:</strong> {{Start Time}}<br>
      <strong>To:</strong> {{End Time}}
    </div>
  </div>

  <!-- Report metadata -->
  <div class="section-title">Report Information</div>
  <div class="info-grid">
    <div class="info-row">
      <span class="info-label">Client / Site</span>
      <span class="info-value">{{Report_Title}}</span>
    </div>
    <div class="info-row">
      <span class="info-label">Generator S/N</span>
      <span class="info-value">{{Gen_SN}}</span>
    </div>
    <div class="info-row">
      <span class="info-label">Site Address</span>
      <span class="info-value">{{Site_Address}}</span>
    </div>
    <div class="info-row">
      <span class="info-label">Test Period</span>
      <span class="info-value">{{Start Time}} – {{End Time}}</span>
    </div>
  </div>

  <!-- Custom notes -->
  <div class="notes-block">
    <div class="notes-label">Notes</div>
    {{Custom_Field}}
  </div>

  <!-- Compliance table -->
  <div class="section-title">Compliance Summary</div>
  <div class="compliance-block">
    {{Compliance_Table}}
  </div>

  <!-- Metric charts -->
  <div class="section-title">Metric Graphs</div>
  <div class="chart-grid">
    <div class="chart-block">
      <div class="chart-label">Voltage (L-L)</div>
      {{Avg_Voltage_LL}}
    </div>
    <div class="chart-block">
      <div class="chart-label">Active Power (kW)</div>
      {{Avg_kW}}
    </div>
    <div class="chart-block">
      <div class="chart-label">Current (A)</div>
      {{Avg_Current}}
    </div>
    <div class="chart-block">
      <div class="chart-label">Frequency (Hz)</div>
      {{Avg_Frequency}}
    </div>
    <div class="chart-block">
      <div class="chart-label">THD (%)</div>
      {{Avg_THD_F}}
    </div>
    <div class="chart-block">
      <div class="chart-label">Power Factor</div>
      {{Avg_PF}}
    </div>
  </div>

  <!-- Event snapshots -->
  <div class="section-title">Event Snapshots</div>
  <div class="snapshot-block">
    <div class="snapshot-title">Event 1</div>
    {{Snapshot_1}}
  </div>
  <div class="snapshot-block">
    <div class="snapshot-title">Event 2</div>
    {{Snapshot_2}}
  </div>
  <div class="snapshot-block">
    <div class="snapshot-title">Event 3</div>
    {{Snapshot_3}}
  </div>
  <div class="snapshot-block">
    <div class="snapshot-title">Event 4</div>
    {{Snapshot_4}}
  </div>
  <div class="snapshot-block">
    <div class="snapshot-title">Event 5</div>
    {{Snapshot_5}}
  </div>
  <div class="snapshot-block">
    <div class="snapshot-title">Event 6</div>
    {{Snapshot_6}}
  </div>
  <div class="snapshot-block">
    <div class="snapshot-title">Event 7</div>
    {{Snapshot_7}}
  </div>
  <div class="snapshot-block">
    <div class="snapshot-title">Event 8</div>
    {{Snapshot_8}}
  </div>
  <div class="snapshot-block">
    <div class="snapshot-title">Event 9</div>
    {{Snapshot_9}}
  </div>
  <div class="snapshot-block">
    <div class="snapshot-title">Event 10</div>
    {{Snapshot_10}}
  </div>

  <!-- Footer -->
  <div class="report-footer">
    <span>Power Quality Analysis — Confidential</span>
    <span>{{Date}}</span>
  </div>

</div>
</body>
</html>
"""


# ── Placeholder injection ──────────────────────────────────────────────────

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


def _file_to_base64_img_tag(file_path: str) -> str:
    """Read an image file and return an <img> tag with base64-encoded src."""
    ext = os.path.splitext(file_path)[1].lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")
    with open(file_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return f'<img src="data:{mime};base64,{data}" style="max-width:100%;height:auto;">'


def inject_html_placeholders(template: str, placeholder_map: dict) -> str:
    """
    Replace {{placeholders}} in an HTML template string.

    Image placeholders (values pointing to .png/.jpg/.jpeg files) are replaced
    with base64-embedded <img> tags. Text placeholders are substituted as-is.
    Missing image files are replaced with an empty string (placeholder silently removed).

    Parameters:
        template: HTML string containing {{PLACEHOLDER}} markers.
        placeholder_map: dict mapping "{{KEY}}" -> file_path_or_text_value.
            Must use the same format produced by report.get_placeholder_map().

    Returns:
        HTML string with all recognised placeholders replaced.
    """
    result = template
    for key, value in placeholder_map.items():
        if not isinstance(value, str):
            value = str(value)
        ext = os.path.splitext(value)[1].lower()
        if ext in _IMAGE_EXTENSIONS:
            if os.path.exists(value):
                replacement = _file_to_base64_img_tag(value)
            else:
                log.warning("HTML report: image not found for placeholder %s: %s", key, value)
                replacement = ""
        else:
            replacement = value
        result = result.replace(key, replacement)
    return result


# ── HTML → PDF conversion ──────────────────────────────────────────────────

def _try_weasyprint(html: str, output_path: str) -> None:
    import weasyprint
    weasyprint.HTML(string=html).write_pdf(output_path)


def _try_libreoffice(html: str, output_path: str) -> None:
    """Write HTML to a temp file then convert via LibreOffice headless."""
    candidates = [
        "libreoffice",
        "soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/usr/bin/libreoffice",
        "/usr/bin/soffice",
        "/snap/bin/libreoffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    lo_bin = None
    for c in candidates:
        try:
            r = subprocess.run([c, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                lo_bin = c
                break
        except Exception:
            continue
    if not lo_bin:
        raise RuntimeError("LibreOffice not found")

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        f.write(html)
        tmp_html = f.name

    try:
        out_dir = os.path.dirname(os.path.abspath(output_path))
        subprocess.run(
            [lo_bin, "--headless", "--convert-to", "pdf", "--outdir", out_dir, tmp_html],
            check=True, capture_output=True, timeout=90,
        )
        expected = os.path.join(out_dir, os.path.splitext(os.path.basename(tmp_html))[0] + ".pdf")
        if os.path.exists(expected) and os.path.abspath(expected) != os.path.abspath(output_path):
            shutil.move(expected, output_path)
    finally:
        try:
            os.unlink(tmp_html)
        except Exception:
            pass


def _try_reportlab(html: str, output_path: str) -> None:
    """
    Fallback: extract text and images from the HTML and build a basic PDF with reportlab.
    Produces a functional but visually simplified result.
    """
    import re
    from io import BytesIO

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    story = []
    margin = 16 * mm
    page_width = A4[0] - 2 * margin

    # Extract base64 images and text blocks from HTML, in document order.
    # We process the HTML as text rather than full DOM parsing.
    b64_img_pattern = re.compile(
        r'<img[^>]+src="data:([^;]+);base64,([^"]+)"[^>]*>', re.IGNORECASE
    )
    text_pattern = re.compile(r'<[^>]+>')

    # Split on img tags to interleave text and images
    segments = b64_img_pattern.split(html)
    # segments alternates: text, mime, b64data, text, mime, b64data, ...
    i = 0
    while i < len(segments):
        chunk = segments[i]
        # Strip tags from text chunk and add non-empty paragraphs
        clean = text_pattern.sub(' ', chunk).strip()
        if clean:
            for line in clean.split('\n'):
                line = line.strip()
                if line:
                    try:
                        story.append(Paragraph(line, styles["Normal"]))
                        story.append(Spacer(1, 2 * mm))
                    except Exception:
                        pass
        # Check if next segments are a mime/b64 pair
        if i + 2 < len(segments):
            # mime_type = segments[i + 1]  (unused but consumed)
            b64_data = segments[i + 2]
            try:
                img_bytes = base64.b64decode(b64_data)
                img_buf = BytesIO(img_bytes)
                rl_img = RLImage(img_buf, width=page_width, height=page_width * 0.6)
                story.append(rl_img)
                story.append(Spacer(1, 4 * mm))
            except Exception as e:
                log.warning("reportlab: failed to decode embedded image: %s", e)
            i += 3
        else:
            i += 1

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
    )
    doc.build(story)


def generate_pdf_from_html(html: str, output_path: str) -> tuple[bool, str]:
    """
    Convert an HTML string to PDF, trying converters in order:
      1. WeasyPrint (best quality; requires cairo/pango system libs — works on Streamlit Cloud)
      2. LibreOffice headless (good quality; requires LibreOffice installed)
      3. reportlab (pure Python fallback; simplified layout)

    Returns:
        (success, log_message)
    """
    converters = [
        ("WeasyPrint", _try_weasyprint),
        ("LibreOffice", _try_libreoffice),
        ("reportlab", _try_reportlab),
    ]
    log_lines = []
    for name, fn in converters:
        try:
            fn(html, output_path)
            if os.path.exists(output_path):
                msg = f"HTML → PDF succeeded via {name}"
                log.info(msg)
                log_lines.append(msg)
                return True, "\n".join(log_lines)
        except Exception as e:
            msg = f"{name} failed: {e}"
            log.warning(msg)
            log_lines.append(msg)
    return False, "\n".join(log_lines)


# ── Full pipeline ──────────────────────────────────────────────────────────

def generate_html_report(
    placeholder_map: dict,
    template_str: str,
    output_name: str = "PQA_Report",
) -> dict:
    """
    Full pipeline: inject placeholders → save HTML → convert to PDF.

    Parameters:
        placeholder_map: from report.get_placeholder_map()
        template_str: the editable HTML template (from session state or default)
        output_name: base path without extension (e.g. "output/MyReport")

    Returns:
        dict with keys:
          "html"  → path to saved .html file (always present)
          "pdf"   → path to PDF if conversion succeeded (may be absent)
          "pdf_log" → conversion diagnostic string
    """
    html_path = f"{output_name}.html"
    html_content = inject_html_placeholders(template_str, placeholder_map)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    log.info("HTML report saved: %s", html_path)

    result: dict = {"html": html_path}

    pdf_path = f"{output_name}.pdf"
    pdf_ok, pdf_log = generate_pdf_from_html(html_content, pdf_path)
    result["pdf_log"] = pdf_log
    if pdf_ok:
        result["pdf"] = pdf_path

    return result
