"""Host-side report builder + Chromium PDF export (desktop only).

Assembles a PQA report from a completed analysis and returns the artifacts as
JSON-safe payloads the frontend turns into downloads:

* **HTML**  — self-contained string (images embedded as base64). Always cheap.
* **PDF**   — produced by the desktop's bundled Chromium (Edge WebView2 on
              Windows). We render the HTML report then print it to PDF with
              ``--headless --print-to-pdf`` — no LibreOffice, no WeasyPrint.
* **.docx** — editable Word document, only when the caller supplies a Word
              template; produced by python-docx via the reused ``report`` helpers.

Reuse, not reinvention: image rendering goes through :mod:`desktop.viz_report`
(which wraps the validated ``visualizations`` renderers); placeholder mapping and
docx/HTML injection reuse ``report.get_placeholder_map`` /
``report.inject_images_to_word`` and ``html_report.get_default_template`` /
``html_report.inject_html_placeholders``. The heavy modules (``report`` needs
python-docx, ``visualizations`` needs matplotlib) are imported **lazily** so this
module imports cleanly under the CI pytest job, which installs only
pandas/numpy/pytest.
"""
from __future__ import annotations

import base64
import logging
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

log = logging.getLogger(__name__)

# Image placeholders that ``report.get_placeholder_map`` only emits when the
# underlying file exists — so they survive injection unmatched when a metric is
# empty or there are fewer events than template snapshot slots. We blank these
# leftovers so the rendered report never shows literal ``{{...}}`` braces.
_UNUSED_IMAGE_PLACEHOLDER = re.compile(
    r"\{\{(?:Snapshot_\d+|Avg_[A-Za-z_]+|Compliance_Table)\}\}")

# Word .docx MIME — surfaced so the frontend tags downloads correctly.
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# ── Chromium / Edge discovery + headless print-to-PDF ───────────────────────────

def find_chromium() -> str | None:
    """Locate a Chromium-family browser for headless PDF printing, or ``None``.

    Order: ``PQA_CHROMIUM``/``PQA_EDGE`` env overrides → names on ``PATH``
    (Edge first, it ships with Windows) → standard Windows install locations.
    """
    for env in ("PQA_CHROMIUM", "PQA_EDGE"):
        p = os.environ.get(env)
        if p and os.path.exists(p):
            return p

    for name in ("msedge", "microsoft-edge", "microsoft-edge-stable",
                 "google-chrome", "google-chrome-stable",
                 "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found

    candidates = []
    for var in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        root = os.environ.get(var)
        if not root:
            continue
        candidates += [
            os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"),
        ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def html_to_pdf(html: str, pdf_path: str, *, timeout: int = 60,
                browser: str | None = None) -> tuple[bool, str]:
    """Render ``html`` to ``pdf_path`` via headless Chromium/Edge print-to-pdf.

    Returns ``(ok, log)``. ``ok`` is whether the PDF file now exists; ``log``
    carries the browser used plus any stderr, for surfacing in the UI.
    """
    browser = browser or find_chromium()
    if not browser:
        return False, (
            "No Chromium/Edge browser found for PDF export. On Windows the Edge "
            "WebView2 runtime/Edge browser provides this; set PQA_CHROMIUM to a "
            "browser path to override."
        )

    tmp_dir = tempfile.mkdtemp(prefix="pqa_pdf_")
    tmp_html = os.path.join(tmp_dir, "report.html")
    profile_dir = os.path.join(tmp_dir, "profile")
    try:
        with open(tmp_html, "w", encoding="utf-8") as f:
            f.write(html)
        file_uri = pathlib.Path(tmp_html).as_uri()
        cmd = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",                      # required for headless Chrome on Linux/CI; harmless on Windows
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile_dir}",
            "--no-pdf-header-footer",            # drop the default date/URL chrome
            f"--print-to-pdf={os.path.abspath(pdf_path)}",
            file_uri,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, f"PDF export timed out after {timeout}s (browser: {browser})."
        except Exception as exc:  # noqa: BLE001
            return False, f"PDF export failed to launch browser {browser}: {exc}"

        ok = os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0
        parts = [f"browser: {browser}"]
        if proc.stderr.strip():
            # Chromium is chatty on stderr even on success; keep the tail only.
            parts.append(proc.stderr.strip()[-800:])
        if not ok and proc.returncode != 0:
            parts.append(f"exit code {proc.returncode}")
        return ok, "\n".join(parts)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Report assembly ─────────────────────────────────────────────────────────────

def default_html_template() -> str:
    """The built-in editable HTML report template (delegates to ``html_report``)."""
    import html_report
    return html_report.get_default_template()


_FORBIDDEN = '<>:"/\\|?*'


def _safe_name(name: str, fallback: str = "PQA_Report") -> str:
    """Filesystem-safe stem: strip path separators and control characters."""
    name = (str(name) if name is not None else "").strip()
    if not name:
        return fallback
    cleaned = "".join("_" if ch in _FORBIDDEN or ord(ch) < 32 else ch for ch in name)
    cleaned = cleaned.strip(" .")
    return cleaned or fallback


def _file_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _strip_unused_image_placeholders(html: str) -> str:
    """Remove leftover image ``{{...}}`` tokens that had no rendered file."""
    return _UNUSED_IMAGE_PLACEHOLDER.sub("", html)


def build_report(df_raw, df_proc, df_events, config, params, *, work_dir=None) -> dict:
    """Build the requested report artifacts from a completed analysis.

    ``params`` (a single JSON object across the bridge)::

        {
          "fields": {report_title, pqa_serial, gen_sn, site_address, custom_text},
          "filename": "PQA_Report",
          "outputs": {"pdf": true, "html": false, "docx": false},
          "html_template": "<...>",          # optional; defaults to built-in
          "docx_template_b64": "<base64>",   # optional; required for .docx output
          "rated_load_kw": 1000,             # optional, for % annotations
          "image_options": {...}             # optional viz_report overrides
        }

    Returns::

        {filename, artifacts: {pdf_b64?, html?, docx_b64?, docx_mime?},
         pdf_ok, warnings: [...], log}
    """
    params = params or {}
    fields = params.get("fields") or {}
    outputs = params.get("outputs") or {"pdf": True}
    filename = _safe_name(params.get("filename") or fields.get("report_title") or "PQA_Report")
    client_name = _safe_name(fields.get("report_title") or filename, fallback=filename)
    html_template = params.get("html_template") or default_html_template()
    docx_template_b64 = params.get("docx_template_b64")
    rated = params.get("rated_load_kw")

    image_options = dict(params.get("image_options") or {})
    if rated is not None:
        image_options.setdefault("rated_load_kw", rated)

    warnings: list[str] = []
    log_lines: list[str] = []
    artifacts: dict = {}
    pdf_ok = False

    owns_dir = work_dir is None
    work_dir = work_dir or tempfile.mkdtemp(prefix="pqa_report_")
    try:
        # 1. Render the images the template embeds (lazy: matplotlib).
        from desktop.viz_report import render_report_images
        img = render_report_images(
            df_raw, df_proc, df_events, config, client_name, work_dir,
            options=image_options or None,
        )
        warnings.extend(img.get("errors", []))

        # 2. Build the {{placeholder}} -> path/text map (lazy: python-docx).
        import report as report_mod
        config_values = {
            "report_title": fields.get("report_title", ""),
            "pqa_serial": fields.get("pqa_serial", ""),
            "gen_sn": fields.get("gen_sn", ""),
            "site_address": fields.get("site_address", ""),
            "custom_text": fields.get("custom_text", ""),
        }
        p_map = report_mod.get_placeholder_map(
            client_name, config_values, df=df_raw,
            graph_dir=img["graph_dir"], snapshot_dir=img["snapshot_dir"],
            image_dir=img["image_dir"],
        )

        # Warn when the template can't fit every detected event's snapshot.
        n_events = 0 if df_events is None else len(df_events)
        n_snap_ph = sum(1 for k in p_map if k.startswith("{{Snapshot_"))
        if n_snap_ph < n_events:
            warnings.append(
                f"Template/render produced {n_snap_ph} snapshot slot(s) but "
                f"{n_events} events were detected; add {{{{Snapshot_{n_snap_ph + 1}}}}}"
                f" … {{{{Snapshot_{n_events}}}}} placeholders to include them all."
            )

        want_html = bool(outputs.get("html"))
        want_pdf = bool(outputs.get("pdf"))
        want_docx = bool(outputs.get("docx"))
        if not (want_html or want_pdf or want_docx):
            want_pdf = True  # sensible default: always give the user something

        # 3. HTML (needed for the html artifact and/or as the PDF source).
        if want_html or want_pdf:
            import html_report
            html_str = _strip_unused_image_placeholders(
                html_report.inject_html_placeholders(html_template, p_map))
            if want_html:
                artifacts["html"] = html_str
            if want_pdf:
                pdf_path = os.path.join(work_dir, filename + ".pdf")
                pdf_ok, plog = html_to_pdf(html_str, pdf_path)
                log_lines.append(plog)
                if pdf_ok:
                    artifacts["pdf_b64"] = _file_b64(pdf_path)
                else:
                    warnings.append("PDF export failed — see report log for details.")

        # 4. Editable Word .docx (only with a supplied template).
        if want_docx:
            if docx_template_b64:
                import io
                doc = report_mod.inject_images_to_word(
                    io.BytesIO(base64.b64decode(docx_template_b64)), p_map)
                docx_path = os.path.join(work_dir, filename + ".docx")
                doc.save(docx_path)
                artifacts["docx_b64"] = _file_b64(docx_path)
                artifacts["docx_mime"] = DOCX_MIME
            else:
                warnings.append("Word (.docx) output needs a Word template upload.")
    finally:
        if owns_dir:
            shutil.rmtree(work_dir, ignore_errors=True)

    return {
        "filename": filename,
        "artifacts": artifacts,
        "pdf_ok": pdf_ok,
        "warnings": warnings,
        "log": "\n".join(line for line in log_lines if line),
    }
