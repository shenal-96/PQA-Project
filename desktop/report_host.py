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
import time

log = logging.getLogger(__name__)

# Image placeholders that ``report.get_placeholder_map`` only emits when the
# underlying file exists — so they survive injection unmatched when a metric is
# empty or there are fewer events than template snapshot slots. We blank these
# leftovers so the rendered report never shows literal ``{{...}}`` braces.
_UNUSED_IMAGE_PLACEHOLDER = re.compile(
    r"\{\{(?:Snapshot_\d+|Avg_[A-Za-z_]+|Compliance_Table|ITIC_Curve)\}\}")

# Word .docx MIME — surfaced so the frontend tags downloads correctly.
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# ── Chromium / Edge discovery + headless print-to-PDF ───────────────────────────

def find_chromium() -> str | None:
    """Locate a Chromium-family browser for headless PDF printing, or ``None``.

    Order: ``PQA_CHROMIUM``/``PQA_EDGE`` env overrides → names on ``PATH``
    (Edge first, it ships with Windows) → standard install locations for the
    current OS (Windows Program Files, macOS ``/Applications`` .app bundles,
    common Linux paths). macOS/Linux browsers are not on ``PATH`` by default, so
    the absolute-path fallback is what makes PDF export work there.
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
    # Windows install locations.
    for var in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        root = os.environ.get(var)
        if not root:
            continue
        candidates += [
            os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"),
        ]
    # macOS .app bundles (not on PATH).
    candidates += [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    # Common Linux absolute paths (in case PATH lookup missed them).
    candidates += [
        "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium", "/usr/bin/chromium-browser",
        "/usr/bin/microsoft-edge", "/snap/bin/chromium",
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
        # Chrome on macOS writes the PDF but does not reliably self-terminate
        # after --print-to-pdf, so we cannot just wait for the process to exit
        # (Edge on Windows does exit — proc.poll() returns first and we stop
        # immediately). Instead: launch, poll for the output file to appear and
        # stop growing, then terminate the process. stderr is sent to a file
        # (not a pipe) so a chatty browser can never fill a pipe buffer and stall
        # the render, and so we never block waiting for a child to close the pipe.
        err_path = os.path.join(tmp_dir, "chrome.err")
        try:
            err_f = open(err_path, "wb")
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err_f)
        except Exception as exc:  # noqa: BLE001
            return False, f"PDF export failed to launch browser {browser}: {exc}"

        abs_pdf = os.path.abspath(pdf_path)
        deadline = time.monotonic() + timeout
        poll_s = 0.25
        stable_needed_s = 0.75  # size must hold steady this long => render done
        last_size = -1
        stable_s = 0.0
        timed_out = True
        try:
            while time.monotonic() < deadline:
                if proc.poll() is not None:  # browser exited on its own (Edge)
                    timed_out = False
                    break
                if os.path.exists(abs_pdf):
                    size = os.path.getsize(abs_pdf)
                    if size > 0 and size == last_size:
                        stable_s += poll_s
                        if stable_s >= stable_needed_s:
                            timed_out = False
                            break
                    else:
                        stable_s = 0.0
                    last_size = size
                time.sleep(poll_s)
        finally:
            if proc.poll() is None:  # macOS: still running after the PDF is done
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            err_f.close()

        ok = os.path.exists(abs_pdf) and os.path.getsize(abs_pdf) > 0
        parts = [f"browser: {browser}"]
        try:
            with open(err_path, "rb") as f:
                stderr_txt = f.read().decode("utf-8", errors="replace").strip()
        except OSError:
            stderr_txt = ""
        if stderr_txt:
            # Chromium is chatty on stderr even on success; keep the tail only.
            parts.append(stderr_txt[-800:])
        if not ok and timed_out:
            parts.append(f"timed out after {timeout}s")
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


def _esc(value) -> str:
    """Minimal HTML-escape for cell text."""
    import html as _html
    return _html.escape("" if value is None else str(value))


def _fmt(value, dp: int = 2) -> str:
    """Format a numeric cell to ``dp`` decimals; em-dash for missing."""
    if value is None:
        return "—"
    try:
        return f"{float(value):.{dp}f}"
    except (TypeError, ValueError):
        return _esc(value)


def build_steady_summary_html(summary) -> str:
    """Render the cross-window ISO 8528-5 steady-state summary — voltage
    regulation ΔU_st, frequency droop sanity, the sample-rate gate, and the
    performance class — as inline-styled HTML, or ``""`` when there is nothing
    to show. Pairs with :func:`build_steady_table_html` (per-window detail)."""
    if not summary or not summary.get("n_windows"):
        return ""
    td = "padding:5px 9px;border:1px solid #e2e8f0;font-size:12px;"

    def _pill(passed) -> str:
        if passed is None:
            return '<span style="color:#64748b;">—</span>'
        css = ("background:#dcfce7;color:#15803d;" if passed
               else "background:#fee2e2;color:#b91c1c;")
        return (f'<span style="padding:1px 8px;border-radius:999px;font-weight:600;'
                f'font-size:11px;{css}">{"Pass" if passed else "Fail"}</span>')

    def _row(label, val, limit, passed, *, dp=3) -> str:
        v = "—" if val is None else f"{_fmt(val, dp)}%"
        lim = "" if limit is None else (f' <span style="color:#64748b;">'
                                        f'(limit {_fmt(limit, 2)}%)</span>')
        return (f'<tr><td style="{td}">{label}</td>'
                f'<td style="{td}font-family:monospace;">{v}{lim}</td>'
                f'<td style="{td}">{_pill(passed)}</td></tr>')

    cls = summary.get("performance_class")
    fs = summary.get("sample_rate_hz")
    head = f"Performance class {_esc(cls)}" if cls else "No performance class (free-form δ bands)"
    if fs is not None:
        head += f" · sample rate {_fmt(fs, 3)} Hz"

    # Voltage unbalance — value + verdict when computed, else the gate status.
    ub_val = summary.get("volt_unbalance_pct")
    if ub_val is None:
        ub_row = (f'<tr><td style="{td}">ΔU_2.0 — voltage unbalance @ no-load</td>'
                  f'<td style="{td}" colspan="2"><span style="color:#64748b;">'
                  f'{_esc(summary.get("volt_unbalance_status"))}</span></td></tr>')
    else:
        ub_lim = summary.get("volt_unbalance_limit_pct")
        ub_v = f"{_fmt(ub_val, 3)}%" + ("" if ub_lim is None else
               f' <span style="color:#64748b;">(limit {_fmt(ub_lim, 2)}%)</span>')
        ub_note = (f'<div style="color:#64748b;font-size:10.5px;">'
                   f'{_esc(summary.get("volt_unbalance_status"))}</div>')
        ub_row = (f'<tr><td style="{td}">ΔU_2.0 — voltage unbalance @ no-load</td>'
                  f'<td style="{td}font-family:monospace;">{ub_v}{ub_note}</td>'
                  f'<td style="{td}">{_pill(summary.get("volt_unbalance_pass"))}</td></tr>')

    out = [
        '<div class="section-title">Steady-State Summary (ISO 8528-5)</div>',
        f'<div style="font-size:12px;color:#475569;margin:2px 0 6px;">{head}</div>',
        '<table style="border-collapse:collapse;margin:0 0 14px;">',
        _row("ΔU_st — voltage regulation (±)", summary.get("delta_u_st_pct"),
             summary.get("delta_u_st_limit_pct"), summary.get("delta_u_st_pass")),
        _row("Frequency droop (sanity)", summary.get("freq_droop_pct"),
             summary.get("freq_droop_limit_pct"), summary.get("freq_droop_pass")),
        ub_row,
        # Modulation — deferred maths; surface the §4 sample-rate gate status.
        f'<tr><td style="{td}">Û_mod,s — voltage modulation</td>'
        f'<td style="{td}" colspan="2"><span style="color:#64748b;">'
        f'{_esc(summary.get("modulation_status"))}</span></td></tr>',
        "</table>",
    ]
    return "\n".join(out)


def build_steady_table_html(df_steady) -> str:
    """Render the steady-state (ISO 8528-5 δ band) results as a self-contained
    HTML section, or ``""`` when there is nothing to show.

    Returned as inline-styled HTML so it survives in the standalone HTML report
    and the Chromium print-to-PDF without depending on the template's CSS. This
    feeds the ``{{Steady_State_Table}}`` text placeholder (text, not an image),
    so the heading lives in here and disappears entirely when there are no
    dwell windows.
    """
    if df_steady is None or len(df_steady) == 0:
        return ""

    rows = df_steady.to_dict("records")
    th = ('padding:6px 9px;border:1px solid #cbd5e1;background:#f1f5f9;'
          'font-size:11px;text-transform:uppercase;letter-spacing:.04em;'
          'color:#475569;text-align:left;')
    td = "padding:6px 9px;border:1px solid #e2e8f0;font-size:12px;"
    out: list[str] = [
        '<div class="section-title">Steady-State Compliance (ISO 8528-5 δ bands)</div>',
        '<table style="border-collapse:collapse;width:100%;margin:6px 0 14px;">',
        "<thead><tr>"
        f'<th style="{th}">Load</th>'
        f'<th style="{th}">Dwell window</th>'
        f'<th style="{th}">Dur (s)</th>'
        f'<th style="{th}">V min/mean/max (V)</th>'
        f'<th style="{th}">V out</th>'
        f'<th style="{th}">F min/mean/max (Hz)</th>'
        f'<th style="{th}">F out</th>'
        f'<th style="{th}">β_f % / limit</th>'
        f'<th style="{th}">Result</th>'
        "</tr></thead><tbody>",
    ]

    def _ts(value) -> str:
        return _esc(value).replace("T", " ").split(".")[0]

    for r in rows:
        is_fail = str(r.get("Status")) == "Fail"
        row_bg = "background:#fef2f2;" if is_fail else ""
        status_css = ("background:#fee2e2;color:#b91c1c;" if is_fail
                      else "background:#dcfce7;color:#15803d;")
        v_out = int(r.get("V_n_out") or 0)
        f_out = int(r.get("F_n_out") or 0)
        v_out_txt = f"{v_out} ({_fmt(r.get('V_pct_out'))}%)" if v_out else "0"
        f_out_txt = f"{f_out} ({_fmt(r.get('F_pct_out'))}%)" if f_out else "0"
        bf, bf_lim, bf_pass = r.get("Beta_f_pct"), r.get("Beta_f_limit_pct"), r.get("Beta_f_pass")
        if bf is None:
            bf_txt = "—"
        elif bf_lim is None:
            bf_txt = _fmt(bf, 3)            # legacy mode: informational, no limit
        else:
            bf_color = "#b91c1c" if bf_pass is False else "#15803d"
            bf_txt = (f'<span style="color:{bf_color};font-weight:600;">{_fmt(bf, 3)}</span>'
                      f' <span style="color:#64748b;">/ {_fmt(bf_lim, 2)}</span>')
        badge = (f'<span style="padding:1px 8px;border-radius:999px;font-weight:600;'
                 f'font-size:11px;{status_css}">{_esc(r.get("Status"))}</span>')
        if r.get("Hunting"):
            badge += ('<span style="padding:1px 8px;border-radius:999px;margin-left:4px;'
                      'background:#fffbeb;color:#b45309;font-size:11px;">⚠ Hunting</span>')
        notes = []
        if r.get("Failure_Reasons"):
            notes.append(_esc(r["Failure_Reasons"]))
        if r.get("Hunting_Reasons"):
            notes.append("⚠ " + _esc(r["Hunting_Reasons"]))
        out.append(
            f'<tr style="{row_bg}">'
            f'<td style="{td}">{_esc(r.get("Load_Label") or "—")}</td>'
            f'<td style="{td}font-family:monospace;font-size:11px;">{_ts(r.get("Start_Timestamp"))}<br>{_ts(r.get("End_Timestamp"))}</td>'
            f'<td style="{td}font-family:monospace;">{_fmt(r.get("Duration_s"), 1)}</td>'
            f'<td style="{td}font-family:monospace;">{_fmt(r.get("V_min"))} / {_fmt(r.get("V_mean"))} / {_fmt(r.get("V_max"))}</td>'
            f'<td style="{td}font-family:monospace;">{v_out_txt}</td>'
            f'<td style="{td}font-family:monospace;">{_fmt(r.get("F_min"), 3)} / {_fmt(r.get("F_mean"), 3)} / {_fmt(r.get("F_max"), 3)}</td>'
            f'<td style="{td}font-family:monospace;">{f_out_txt}</td>'
            f'<td style="{td}font-family:monospace;">{bf_txt}</td>'
            f'<td style="{td}">{badge}</td>'
            "</tr>"
        )
        if notes:
            out.append(
                f'<tr style="{row_bg}"><td colspan="9" '
                f'style="{td}color:#64748b;font-size:11px;">{" · ".join(notes)}</td></tr>'
            )

    out.append("</tbody></table>")
    return "\n".join(out)


def _strip_unused_image_placeholders(html: str) -> str:
    """Remove leftover image ``{{...}}`` tokens that had no rendered file."""
    return _UNUSED_IMAGE_PLACEHOLDER.sub("", html)


def build_report(df_raw, df_proc, df_events, config, params, *, df_steady=None, work_dir=None) -> dict:
    """Build the requested report artifacts from a completed analysis.

    ``params`` (a single JSON object across the bridge)::

        {
          "fields": {report_title, pqa_serial, gen_sn, site_address, custom_text},
          "filename": "PQA_Report",
          "outputs": {"pdf": true, "html": false, "docx": false},
          "html_template": "<...>",          # optional; defaults to built-in
          "docx_template_b64": "<base64>",   # optional; inline .docx for output
          "docx_template_name": "Acme.docx", # optional; name in the saved library
          "clear_not_recovered": false,      # optional; drop the not-recovered flags
          "include_compliance_table": false, # optional; add compliance table even
                                             #   when the template has no placeholder
          "include_itic": false,             # optional; render + add the ITIC curve
          "rated_load_kw": 1000,             # optional, for % annotations
          "image_options": {...},            # optional viz_report overrides
          "snapshot_window_overrides": {"0": 12.0},  # optional per-event window (s)
          "snapshot_offset_overrides": {"0": -1.5},  # optional per-event time-shift (s)
        }

    ``include_compliance_table`` / ``include_itic`` add those sections after the
    results/time-series block and before the snapshots. In the .docx they are
    injected as Heading-1 sections (so the TOC field lists them) and ``updateFields``
    is set so Word refreshes the contents page on open; if the template already has
    the placeholder, it is filled in place instead.

    ``snapshot_window_overrides`` / ``snapshot_offset_overrides`` are keyed by the
    positional event index (matching the on-screen snapshot tweaks); they are
    remapped onto the df_events index inside ``render_report_images`` so the
    report's clean snapshots match what the user tuned per event.

    A Word template may be supplied inline (``docx_template_b64``) or by the name
    of a template saved in the persistent library (``docx_template_name``); the
    inline form wins when both are present.

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
    docx_template_name = params.get("docx_template_name")
    rated = params.get("rated_load_kw")

    # Report toggles: include the compliance summary table and/or the ITIC curve
    # even when the template has no placeholder for them (injected as new sections).
    include_compliance_table = bool(params.get("include_compliance_table"))
    include_itic = bool(params.get("include_itic"))

    image_options = dict(params.get("image_options") or {})
    if rated is not None:
        image_options.setdefault("rated_load_kw", rated)
    if include_itic:
        image_options["include_itic"] = True
    # When the user opts to drop the not-recovered flags from the report, render
    # the snapshots without the red watermark/tint (mirrors the Streamlit
    # "Remove warnings from report" path, which zeroed the flags before render).
    if params.get("clear_not_recovered"):
        image_options["clear_not_recovered"] = True

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
            snapshot_window_overrides=params.get("snapshot_window_overrides"),
            snapshot_offset_overrides=params.get("snapshot_offset_overrides"),
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
        # Steady-state (ISO 8528-5) — cross-window summary (ΔU_st, droop, gate)
        # followed by the per-window table. A text/HTML placeholder, so it is
        # always set (to "" when there is no steady-state data) and never leaks
        # literal {{braces}} into the rendered report.
        steady_html = build_steady_table_html(df_steady)
        if steady_html:
            import core.analysis as ca
            steady_summary = ca.summarize_steady_state(df_proc, df_steady, config)
            steady_html = build_steady_summary_html(steady_summary) + steady_html
        p_map["{{Steady_State_Table}}"] = steady_html

        # Warn when the template can't fit every detected event's snapshot.
        n_events = 0 if df_events is None else len(df_events)
        n_snap_ph = sum(1 for k in p_map if k.startswith("{{Snapshot_"))
        if n_snap_ph < n_events:
            warnings.append(
                f"Template/render produced {n_snap_ph} snapshot slot(s) but "
                f"{n_events} events were detected; add {{{{Snapshot_{n_snap_ph + 1}}}}}"
                f" … {{{{Snapshot_{n_events}}}}} placeholders to include them all."
            )

        # Toggled extra sections (Compliance Table / ITIC Curve). Each entry is
        # (title, placeholder_key, image_path); the Word and HTML paths inject it
        # only when the template lacks that placeholder.
        extra_sections = []
        if include_compliance_table:
            ct = p_map.get("{{Compliance_Table}}")
            if ct:
                extra_sections.append(("Compliance Summary", "{{Compliance_Table}}", ct))
            else:
                warnings.append(
                    "Compliance table requested but none was produced (no events?).")
        if include_itic:
            ic = p_map.get("{{ITIC_Curve}}")
            if ic:
                extra_sections.append(("ITIC (CBEMA) Curve", "{{ITIC_Curve}}", ic))
            else:
                warnings.append(
                    "ITIC curve requested but none was produced (no plottable events?).")

        want_html = bool(outputs.get("html"))
        want_pdf = bool(outputs.get("pdf"))
        want_docx = bool(outputs.get("docx"))
        if not (want_html or want_pdf or want_docx):
            want_pdf = True  # sensible default: always give the user something

        # Insert toggled sections into the HTML (before the snapshots block) when
        # the template doesn't already carry that placeholder. They reuse the
        # normal placeholder mechanism, so inject_html_placeholders embeds them.
        if (want_html or want_pdf) and extra_sections:
            frag = ""
            for title, ph_key, _path in extra_sections:
                if ph_key in html_template:
                    continue
                frag += (f'  <div class="section-title">{title}</div>\n'
                         f'  <div class="compliance-block">{ph_key}</div>\n')
            if frag:
                marker = '<div class="section-title">Event Snapshots</div>'
                if marker in html_template:
                    html_template = html_template.replace(marker, frag + "  " + marker, 1)
                else:
                    html_template += frag

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

        # 4. Editable Word .docx (only with a supplied template — inline bytes or
        #    a name in the persistent library).
        if want_docx:
            import io
            template_stream = None
            if docx_template_b64:
                template_stream = io.BytesIO(base64.b64decode(docx_template_b64))
            elif docx_template_name:
                from desktop import template_store
                tpl_path = template_store.resolve(docx_template_name)
                if tpl_path:
                    template_stream = tpl_path  # python-docx accepts a path
                else:
                    warnings.append(
                        f"Word template '{docx_template_name}' was not found in the "
                        f"library — re-upload it to generate the .docx.")
            if template_stream is not None:
                doc = report_mod.inject_images_to_word(
                    template_stream, p_map,
                    extra_sections=extra_sections or None,
                    update_fields=bool(extra_sections),
                )
                docx_path = os.path.join(work_dir, filename + ".docx")
                doc.save(docx_path)
                artifacts["docx_b64"] = _file_b64(docx_path)
                artifacts["docx_mime"] = DOCX_MIME
            elif not warnings or "not found" not in warnings[-1]:
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
