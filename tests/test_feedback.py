"""Tests for in-app feedback (feature request / bug report) emailing.

The desktop app is fully offline, so "email the developer" means building a
``mailto:`` pre-addressed to ``usage_log.DEVELOPER_EMAIL`` and opening the user's
mail client. These tests stub ``webbrowser.open`` to capture the URL instead of
launching a real mail client, and assert the contract the frontend relies on.
"""
from __future__ import annotations

import os
import sys
import urllib.parse

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

import desktop.feedback_report as fr          # noqa: E402
from desktop import usage_log                 # noqa: E402
from desktop.shell import HostBridge          # noqa: E402


def _capture_mailto(monkeypatch) -> list[str]:
    """Patch webbrowser.open to record opened URLs; report success."""
    opened: list[str] = []

    def fake_open(url, *args, **kwargs):
        opened.append(url)
        return True

    monkeypatch.setattr(fr.webbrowser, "open", fake_open)
    return opened


def _parsed_query(mailto: str) -> dict[str, str]:
    qs = urllib.parse.urlparse(mailto).query
    return {k: v[0] for k, v in urllib.parse.parse_qs(qs).items()}


def test_feature_request_opens_mailto_to_developer(monkeypatch):
    opened = _capture_mailto(monkeypatch)

    result = fr.send_feedback("feature", "Please add an Excel export", app_version="v4.2")

    assert result["ok"] is True
    assert result["mailto_opened"] is True
    assert result["email"] == usage_log.DEVELOPER_EMAIL
    assert len(opened) == 1
    assert opened[0].startswith(f"mailto:{usage_log.DEVELOPER_EMAIL}?")
    q = _parsed_query(opened[0])
    assert q["subject"] == "PQA Desktop — Feature request"
    assert "Please add an Excel export" in q["body"]
    assert "v4.2" in q["body"]


def test_bug_report_uses_bug_subject(monkeypatch):
    opened = _capture_mailto(monkeypatch)

    result = fr.send_feedback("bug", "Frequency plot is blank after Run Analysis")

    assert result["ok"] is True
    q = _parsed_query(opened[0])
    assert q["subject"] == "PQA Desktop — Bug report"
    assert "Frequency plot is blank" in q["body"]


def test_empty_message_does_not_open_mail(monkeypatch):
    opened = _capture_mailto(monkeypatch)

    result = fr.send_feedback("feature", "   ")

    assert result["ok"] is False
    assert result["error"] == "empty message"
    assert opened == []


def test_unknown_kind_falls_back_to_feature(monkeypatch):
    opened = _capture_mailto(monkeypatch)

    result = fr.send_feedback("nonsense", "hello")

    assert result["ok"] is True
    q = _parsed_query(opened[0])
    assert q["subject"] == "PQA Desktop — Feature request"


def test_message_is_truncated_to_url_safe_length(monkeypatch):
    opened = _capture_mailto(monkeypatch)

    fr.send_feedback("bug", "x" * 5000)

    q = _parsed_query(opened[0])
    # The user's text is capped; the body also carries the header/footer lines.
    assert q["body"].count("x") == fr._MAILTO_BODY_CHARS


def test_bridge_email_feedback_contract(monkeypatch):
    opened = _capture_mailto(monkeypatch)

    result = HostBridge().email_feedback({"kind": "bug", "message": "it broke"})

    assert result["ok"] is True
    assert result["email"] == usage_log.DEVELOPER_EMAIL
    assert result["mailto_opened"] is True
    assert len(opened) == 1
    # The bridge stamps the desktop app version into the report body.
    q = _parsed_query(opened[0])
    assert "v4.2" in q["body"]
