# ADR 0001 — Windows-first desktop app, architected iPad-ready

Status: accepted (2026-06-20) · Supersedes the Streamlit-only delivery.

## Context
PQA ships today as a Streamlit app (`app.py`) over a UI-free engine
(`analysis.py`, `visualizations.py`). We need a custom, higher-fidelity UI off
Streamlit, delivered first as a **fully local Windows x86-64 desktop app**, with
an **iPad app later** as a limited-feature (Compliance-CSV-only) subset.

## Decisions
1. **Web UI inside a desktop shell, not native Qt.** The frontend is HTML/CSS/JS
   + Apache ECharts, rendered by **PyWebview / WebView2 (Edge Chromium)**. A web
   UI is the only one reusable on a future iPad (Safari/PWA) and gives the custom
   look + interactive charts we want.
2. **Runs 100% locally — no server.** UI files load from local disk; JS<->Python
   is PyWebview's **in-process bridge** (`window.pywebview.api.*`), not HTTP. No
   ports, no localhost service, no cloud. Ships in one PyInstaller `.exe`,
   offline.
3. **Analysis runs in native host Python now** (fast, every library available),
   **not Pyodide.** Pyodide is taken on later, only for the iPad port.
4. **Reports: editable `.docx` (python-docx) + PDF via the shell's Chromium**
   (WebView2 `PrintToPdf` / headless `msedge --print-to-pdf`). **LibreOffice and
   WeasyPrint are dropped.**
5. **Same repo, dev branch.** The Streamlit app stays runnable throughout via a
   root `analysis.py` re-export shim pointing at `core/analysis.py`. Cutover is a
   merge when the desktop app is done.

## iPad-readiness seams (built now, cheap)
- **Shared pure core** (`core/`): `analysis.py` is kept free of host-only deps in
  the CSV/compliance path so it runs unchanged in Pyodide later.
- **JSON data contract** (`core/serialize.py`): every backend returns the same
  JSON shapes; the UI never knows which backend it talks to.
- **Backend adapter seam** (frontend): UI depends on an `AnalysisBackend`
  interface; ship `PyWebviewBackend` now, add `PyodideBackend` later.
- **Capability gating**: `caps = {platform, canReport, canXls}`; iPad reports
  `canReport=false, canXls=false`.

## Consequences
- Engine correctness is protected by a golden **parity harness**
  (`tests/test_parity.py`) — the same harness will later assert Pyodide == host.
- `python_calamine` (XLS) and reports stay host-only; the iPad subset excludes
  them, so this costs nothing.
- New host deps in `desktop/requirements.txt`; `streamlit`, `weasyprint`,
  `docx2pdf`, `fpdf2`, `reportlab`, `mammoth` and `packages.txt` are removed at
  cutover.
