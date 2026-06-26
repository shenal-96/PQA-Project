"""Tests for the persistent Word-template library (desktop.template_store) and
its HostBridge surface.

These are CI-safe: a minimal hand-built ``.docx`` (a zip with the right parts) is
used so the save/list/delete/resolve plumbing is exercised without python-docx.
The ``{{Snapshot_N}}`` scan needs python-docx, so its assertions ``importorskip``.
"""
from __future__ import annotations

import base64
import io
import os
import sys
import zipfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from desktop import template_store               # noqa: E402
from desktop.shell import HostBridge             # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Point the app-data dir at a temp path so tests never touch real templates."""
    monkeypatch.setenv("PQA_DATA_DIR", str(tmp_path))
    yield


def _minimal_docx_b64(snapshot_text: str = "{{Snapshot_1}} {{Snapshot_2}}") -> str:
    """A real (minimal) .docx: a zip with the document part holding placeholders."""
    body = (
        '<?xml version="1.0"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body><w:p><w:r><w:t>{snapshot_text}</w:t></w:r></w:p></w:body></w:document>'
    )
    content_types = (
        '<?xml version="1.0"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", body)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_save_list_delete_roundtrip(tmp_path):
    assert template_store.list_templates() == []

    out = template_store.save_template("Acme Report.docx", _minimal_docx_b64())
    assert len(out) == 1
    info = out[0]
    assert info["name"] == "Acme Report.docx"
    assert info["size"] > 0

    # Listed again independently.
    assert [t["name"] for t in template_store.list_templates()] == ["Acme Report.docx"]

    after = template_store.delete_template("Acme Report.docx")
    assert after == []


def test_save_sanitises_name_and_forces_docx():
    template_store.save_template("../../evil name.txt", _minimal_docx_b64())
    names = [t["name"] for t in template_store.list_templates()]
    assert names == ["evil name.docx"]            # path stripped, extension forced


def test_resolve_rejects_traversal_and_missing():
    template_store.save_template("good.docx", _minimal_docx_b64())
    assert template_store.resolve("good.docx") is not None
    assert template_store.resolve("") is None
    assert template_store.resolve("nope.docx") is None
    # A traversal attempt resolves to a sanitised name inside the dir, never escapes.
    escaped = template_store.resolve("../../../etc/passwd")
    assert escaped is None or os.path.dirname(escaped) == template_store.templates_dir()


def test_snapshot_scan_indices():
    pytest.importorskip("docx")
    template_store.save_template(
        "snaps.docx", _minimal_docx_b64("{{Snapshot_1}} {{Snapshot_3}} {{Snapshot_2}}"))
    info = next(t for t in template_store.list_templates() if t["name"] == "snaps.docx")
    assert info["snapshot_indices"] == [1, 2, 3]
    assert info["snapshot_max"] == 3


def test_bridge_template_methods():
    bridge = HostBridge()
    assert bridge.list_templates() == {"templates": []}

    saved = bridge.save_template({"filename": "B.docx", "b64": _minimal_docx_b64()})
    assert [t["name"] for t in saved["templates"]] == ["B.docx"]

    listed = bridge.list_templates()
    assert [t["name"] for t in listed["templates"]] == ["B.docx"]

    removed = bridge.delete_template({"name": "B.docx"})
    assert removed == {"templates": []}
