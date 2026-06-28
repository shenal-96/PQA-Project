"""Tests for the M3 report path: desktop.report_host + HostBridge report methods.

Two tiers:
  * Pure tests (no matplotlib/python-docx) run everywhere, incl. the CI pytest
    job which installs only pandas/numpy/pytest.
  * Full report-build tests need matplotlib (images) and python-docx (placeholder
    map / docx injection); they ``importorskip`` so they run locally and skip in
    the lean CI job. The Chromium render itself is exercised with a fake browser
    so the subprocess wiring is covered without a real browser (the real render
    is Windows/Edge-verified).
"""
from __future__ import annotations

import base64
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import core.analysis as ca                                  # noqa: E402
from desktop import report_host                             # noqa: E402
from desktop.shell import HostBridge                        # noqa: E402

FIXTURE = os.path.join(_HERE, "fixtures", "hioki_sample.csv")


def _b64_fixture() -> str:
    with open(FIXTURE, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _frames():
    df = ca.load_and_prepare_csv(FIXTURE)
    df_proc, df_events = ca.perform_analysis(df, ca.AnalysisConfig())
    return df, df_proc, df_events.reset_index(drop=True), ca.AnalysisConfig()


def _write_fake_chromium(tmp_path) -> str:
    """A stand-in browser that honours ``--print-to-pdf=PATH`` like Chromium."""
    script = tmp_path / "fake_chromium.py"
    script.write_text(
        "import sys\n"
        "out = next(a.split('=',1)[1] for a in sys.argv if a.startswith('--print-to-pdf='))\n"
        "uri = [a for a in sys.argv[1:] if not a.startswith('-')][-1]\n"
        "assert uri.startswith('file://'), uri\n"
        "open(out,'wb').write(b'%PDF-1.4\\n%fake\\n%%EOF\\n')\n"
    )
    launcher = tmp_path / "fake_chromium.sh"
    launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
    os.chmod(launcher, 0o755)
    return str(launcher)


# ── Pure tests (CI-safe) ────────────────────────────────────────────────────────

def test_find_chromium_returns_str_or_none():
    assert report_host.find_chromium() is None or isinstance(report_host.find_chromium(), str)


def test_safe_name_sanitises_and_falls_back():
    assert report_host._safe_name("a/b\\c:d*e") == "a_b_c_d_e"
    assert report_host._safe_name("   ") == "PQA_Report"
    assert report_host._safe_name("", fallback="X") == "X"
    assert report_host._safe_name("Acme Genset 2026") == "Acme Genset 2026"


def test_default_html_template_has_placeholders():
    tpl = report_host.default_html_template()
    assert "{{Report_Title}}" in tpl and "{{Compliance_Table}}" in tpl and "{{Snapshot_1}}" in tpl


def test_strip_unused_image_placeholders():
    html = "<p>{{Snapshot_3}}</p><p>{{Avg_THD_F}}</p><p>{{Compliance_Table}}</p><p>{{Report_Title}}</p>"
    out = report_host._strip_unused_image_placeholders(html)
    assert "{{Snapshot_3}}" not in out and "{{Avg_THD_F}}" not in out and "{{Compliance_Table}}" not in out
    assert "{{Report_Title}}" in out  # text placeholders are left for injection


def test_html_to_pdf_no_browser_is_graceful():
    ok, log = report_host.html_to_pdf("<h1>x</h1>", "/tmp/should_not_exist.pdf",
                                      browser="/nonexistent/browser-binary")
    assert ok is False
    assert "browser" in log.lower()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX fake-browser shim")
def test_html_to_pdf_with_fake_browser(tmp_path):
    browser = _write_fake_chromium(tmp_path)
    pdf_path = str(tmp_path / "out.pdf")
    ok, log = report_host.html_to_pdf("<h1>hello</h1>", pdf_path, browser=browser)
    assert ok is True
    assert os.path.exists(pdf_path)
    with open(pdf_path, "rb") as f:
        assert f.read(5) == b"%PDF-"


def test_save_dialog_graceful_without_window():
    # No webview running in tests -> returns path None rather than raising.
    res = HostBridge().save_dialog({"filename": "x.pdf", "data_b64": base64.b64encode(b"x").decode()})
    assert res["path"] is None


def test_save_dialog_requires_data():
    with pytest.raises(ValueError):
        HostBridge().save_dialog({"filename": "x.pdf"})


def test_generate_report_requires_analysis():
    with pytest.raises(RuntimeError):
        HostBridge().generate_report({"outputs": {"html": True}})


def test_remap_overrides_positional_to_index_label():
    """Per-event snapshot overrides (port of #21): the frontend keys them by
    POSITIONAL event index (0..n-1); _remap_overrides translates those onto the
    df_events index labels that generate_all_snapshots looks up — correct even
    when df_events does not carry a default RangeIndex."""
    import pandas as pd
    from desktop.viz_report import _remap_overrides

    df_events = pd.DataFrame({"x": [1, 2, 3]}, index=[10, 20, 30])
    # String keys (as they arrive over the JSON bridge); out-of-range dropped.
    out = _remap_overrides(df_events, {"0": 12.0, "2": 7, "5": 99})
    assert out == {10: 12.0, 30: 7.0}
    # Nothing-to-apply cases collapse to None.
    assert _remap_overrides(df_events, None) is None
    assert _remap_overrides(df_events, {}) is None
    assert _remap_overrides(pd.DataFrame(), {"0": 1.0}) is None


# ── Full report build (needs matplotlib + python-docx) ──────────────────────────

def test_build_report_html(tmp_path):
    pytest.importorskip("matplotlib")
    pytest.importorskip("docx")
    df_raw, df_proc, df_events, cfg = _frames()
    res = report_host.build_report(
        df_raw, df_proc, df_events, cfg,
        {"fields": {"report_title": "Acme Genset", "gen_sn": "GS-1234",
                    "site_address": "12 Test Rd", "custom_text": "Site notes"},
         "filename": "Acme", "outputs": {"html": True, "pdf": False, "docx": False}},
    )
    assert res["filename"] == "Acme"
    html = res["artifacts"]["html"]
    assert "Acme Genset" in html and "GS-1234" in html and "Site notes" in html
    assert "data:image/" in html                       # images embedded as base64
    assert "{{" not in html                            # no residual placeholders
    assert "pdf_b64" not in res["artifacts"]


def test_render_report_images_threads_snapshot_overrides(tmp_path, monkeypatch):
    """render_report_images forwards the per-event window/time-shift overrides to
    generate_all_snapshots, remapped onto the df_events index (port of #21)."""
    pytest.importorskip("matplotlib")
    import pandas as pd
    import visualizations as viz
    from desktop import viz_report

    # Synthetic, non-default index so the positional→label remap is observable.
    df_events = pd.DataFrame({"x": [1, 2, 3]}, index=[10, 20, 30])
    captured: dict = {}

    def fake_snaps(*_a, **k):
        captured["window_overrides"] = k.get("window_overrides")
        captured["offset_overrides"] = k.get("offset_overrides")
        return [], []

    # Stub the matplotlib renderers so the test only exercises the threading.
    monkeypatch.setattr(viz, "generate_all_snapshots", fake_snaps)
    monkeypatch.setattr(viz, "generate_plots", lambda *a, **k: ([], []))
    monkeypatch.setattr(viz, "save_compliance_table_as_image", lambda *a, **k: None)

    viz_report.render_report_images(
        pd.DataFrame(), pd.DataFrame(), df_events, ca.AnalysisConfig(),
        "client", str(tmp_path),
        snapshot_window_overrides={"0": 12.0, "1": 8.0},
        snapshot_offset_overrides={"0": -1.5},
    )
    assert captured["window_overrides"] == {10: 12.0, 20: 8.0}
    assert captured["offset_overrides"] == {10: -1.5}


def test_build_report_docx_needs_template(tmp_path):
    pytest.importorskip("matplotlib")
    pytest.importorskip("docx")
    df_raw, df_proc, df_events, cfg = _frames()
    res = report_host.build_report(
        df_raw, df_proc, df_events, cfg,
        {"fields": {"report_title": "Acme"}, "outputs": {"docx": True, "pdf": False}},
    )
    assert "docx_b64" not in res["artifacts"]
    assert any("template" in w.lower() for w in res["warnings"])


def test_build_report_docx_with_template(tmp_path):
    pytest.importorskip("matplotlib")
    docx = pytest.importorskip("docx")
    import io

    doc = docx.Document()
    doc.add_heading("PQA — {{Report_Title}}", 0)
    doc.add_paragraph("Gen: {{Gen_SN}}")
    doc.add_paragraph("{{Compliance_Table}}")
    doc.add_paragraph("{{Snapshot_1}}")
    buf = io.BytesIO()
    doc.save(buf)

    df_raw, df_proc, df_events, cfg = _frames()
    res = report_host.build_report(
        df_raw, df_proc, df_events, cfg,
        {"fields": {"report_title": "Acme", "gen_sn": "GS-1"},
         "outputs": {"docx": True, "pdf": False},
         "docx_template_b64": base64.b64encode(buf.getvalue()).decode("ascii")},
    )
    assert res["artifacts"]["docx_mime"].endswith("wordprocessingml.document")
    raw = base64.b64decode(res["artifacts"]["docx_b64"])
    assert raw[:2] == b"PK"                              # valid docx (zip)
    out = docx.Document(io.BytesIO(raw))
    assert "Acme" in "\n".join(p.text for p in out.paragraphs)


def test_build_report_docx_from_named_template(tmp_path, monkeypatch):
    """A Word template saved in the library is resolved by name for output."""
    pytest.importorskip("matplotlib")
    docx = pytest.importorskip("docx")
    import io

    from desktop import template_store

    monkeypatch.setenv("PQA_DATA_DIR", str(tmp_path))
    doc = docx.Document()
    doc.add_heading("PQA — {{Report_Title}}", 0)
    doc.add_paragraph("{{Snapshot_1}}")
    buf = io.BytesIO()
    doc.save(buf)
    template_store.save_template("Lib.docx", base64.b64encode(buf.getvalue()).decode("ascii"))

    df_raw, df_proc, df_events, cfg = _frames()
    res = report_host.build_report(
        df_raw, df_proc, df_events, cfg,
        {"fields": {"report_title": "Acme"},
         "outputs": {"docx": True, "pdf": False},
         "docx_template_name": "Lib.docx"},
    )
    assert res["artifacts"]["docx_mime"].endswith("wordprocessingml.document")
    assert base64.b64decode(res["artifacts"]["docx_b64"])[:2] == b"PK"


def test_build_report_named_template_missing_warns(tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    pytest.importorskip("docx")
    monkeypatch.setenv("PQA_DATA_DIR", str(tmp_path))
    df_raw, df_proc, df_events, cfg = _frames()
    res = report_host.build_report(
        df_raw, df_proc, df_events, cfg,
        {"fields": {"report_title": "Acme"},
         "outputs": {"docx": True, "pdf": False},
         "docx_template_name": "Ghost.docx"},
    )
    assert "docx_b64" not in res["artifacts"]
    assert any("not found" in w.lower() for w in res["warnings"])


def test_build_report_clear_not_recovered_option(tmp_path):
    """``clear_not_recovered`` is accepted and produces a clean HTML report."""
    pytest.importorskip("matplotlib")
    pytest.importorskip("docx")
    df_raw, df_proc, df_events, cfg = _frames()
    res = report_host.build_report(
        df_raw, df_proc, df_events, cfg,
        {"fields": {"report_title": "Acme"},
         "outputs": {"html": True, "pdf": False},
         "clear_not_recovered": True},
    )
    assert "{{" not in res["artifacts"]["html"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX fake-browser shim")
def test_generate_report_pdf_via_bridge(tmp_path):
    pytest.importorskip("matplotlib")
    pytest.importorskip("docx")
    browser = _write_fake_chromium(tmp_path)
    os.environ["PQA_CHROMIUM"] = browser
    try:
        bridge = HostBridge()
        bridge.load_csv({"csv_b64": _b64_fixture()})
        bridge.run_analysis({})
        res = bridge.generate_report({"fields": {"report_title": "Acme"},
                                      "filename": "Acme", "outputs": {"pdf": True}})
        assert res["pdf_ok"] is True
        assert base64.b64decode(res["artifacts"]["pdf_b64"])[:5] == b"%PDF-"
    finally:
        os.environ.pop("PQA_CHROMIUM", None)


def test_default_html_template_via_bridge():
    assert "{{Report_Title}}" in HostBridge().default_html_template()["template"]
