# PQA Desktop Migration — Roadmap & Status

Durable, in-repo source of truth for the Streamlit → desktop migration. Any
session (or Codex) should read this **and** `CLAUDE.md` before continuing.

## Context
Move PQA off Streamlit to a **fully-local Windows x86-64 desktop app** with a
custom, higher-fidelity UI — architected so a future **iPad PWA** (Compliance-CSV
only) is a contained add-on. The validated analysis engine is reused as-is; only
the UI layer is rebuilt.

## Branch / PR — READ FIRST
- **All work is on branch `claude/bold-pasteur-zoi0gk` (PR #27).**
- **`main` is intentionally untouched** (the live Streamlit app). **Never branch
  the migration off `main`** — it has none of this code. Always:
  ```bash
  git fetch origin && git checkout claude/bold-pasteur-zoi0gk && git pull
  ```
- It is **one evolving PR**, not one-PR-per-milestone. Keep pushing to this branch.
- The legacy Streamlit app still runs (`streamlit run app.py`); root `analysis.py`
  is now a shim re-exporting `core/analysis.py`, so it keeps working during migration.

## Architecture (how it runs)
- **Web UI** (`web/` — Svelte 5 + Vite + TS + Apache ECharts) rendered inside a
  **PyWebview / WebView2 (Edge Chromium)** desktop shell. **100% local**: the UI is
  a single self-contained `index.html` loaded from `file://`; JS↔Python is
  PyWebview's **in-process bridge** (`window.pywebview.api.*`) — no web server, no
  network, ships in one PyInstaller `.exe`, runs offline.
- **Host Python** runs analysis/plots/reports/XLS natively.
- **iPad-ready seams (built now):** UI depends only on the `AnalysisBackend`
  interface (`web/src/backend/`); the **JSON contract** lives in `core/serialize.py`
  so a future `PyodideBackend` returns identical shapes; `core/` stays pure
  pandas/numpy; capability gating via `caps {platform, canReport, canXls}`.

## Repo layout
```
core/      analysis.py (engine, moved) · serialize.py (JSON contract) ·
           viz_dataprep.py (chart/snapshot data-prep) · recalc.py (overrides)
web/       Svelte app; src/backend/ (AnalysisBackend, PyWebviewBackend, MockBackend),
           src/lib/ (charts, table, sidebar, EventCard, SnapshotChart),
           src/config/ (defaults + ISO presets); scripts/gen_sample.py
desktop/   shell.py (PyWebview + HostBridge) · pqa.spec (PyInstaller) ·
           requirements.txt   [report_host.py / xls_host.py / viz_report.py = TODO M3/M4]
tests/     parity harness (golden) + snapshot/recalc/contract/hostbridge tests
docs/      adr/0001 · run-windows-parallels.md
.github/workflows/  tests.yml (pytest matrix + web build) · package-windows.yml (.exe artifact)
visualizations.py · report.py · html_report.py · ecu_*.py · tracking.py  (host-native, kept at root)
```

## Status by milestone
- **M0 ✅** Monorepo scaffold, engine → `core/`, backend seam + JSON contract, deps rewrite (`desktop/requirements.txt`).
- **M1 ✅** PyWebview shell + `HostBridge` (load_csv/run_analysis/metric_series), first ECharts chart + events table, **parity harness** (golden numbers, CI).
- **M2 ✅** Full **Compliance tab**: config sidebar (all `AnalysisConfig` fields), ISO 8528 presets, 6 metric charts, compliance table (pills/fault badge), **4-panel event snapshots**, **deferred streaming**, **per-event overrides + Recalculate** (`core/recalc.py`), Industrial-Precision design system.
- **M3 ⏳ Reports** — editable `.docx` (python-docx) + PDF via the shell's Chromium (WebView2 `PrintToPdf` / headless `msedge --print-to-pdf`); hi-DPI matplotlib report images. Delete LibreOffice/WeasyPrint chains in `report.py`/`html_report.py`.
  - New: `desktop/report_host.py`, `desktop/viz_report.py`; `HostBridge.generate_report/export_pdf/save_dialog`; gate UI on `caps.canReport`. Reports re-run `perform_analysis` host-side (parity). Reuse `report.get_placeholder_map/inject_images_to_word/generate_docx`, `html_report.get_default_template/inject_html_placeholders`.
- **M4 ⏳ Other tabs (host XLS via python_calamine)** — WinScope (`.xls` → `analysis.load_winscope_xls` → `perform_analysis(skip_interpolation=True)` → reuse Compliance UI), Set Point Comparison (`ecu_parser`/`ecu_csv_parser`/`ecu_multi_comparator`/`ecu_csv_comparator`), ECU Plotting (`ecu_recording_parser` → ECharts per group). New `desktop/xls_host.py`; `caps.canXls`.
- **M5 ⏳ Packaging & polish** — PyInstaller (`desktop/pqa.spec`, done first-cut) + **Inno Setup** installer that silently installs the **WebView2 Evergreen Runtime** AND the **.NET Desktop Runtime** (pywebview needs WinForms via .NET — see Platform notes); telemetry de-Streamlit (`tracking._get_secret` → env); remove dead deps + `packages.txt`; retire `app.py` after parity sign-off.
- **Deferred — iPad PWA:** `PyodideBackend` (Pyodide web worker, same JSON contract), PWA manifest/service worker, Pyodide runtime cached in IndexedDB, COOP/COEP hosting. Reuse the parity golden corpus to assert Pyodide == host.

## Build / run / test
```bash
# Python engine + bridge tests (the parity harness is the central correctness guard)
pip install "pandas>=2.2,<3" numpy pytest
python -m pytest tests/ -q

# Web UI
cd web && npm install && npm run build && npm run check    # build -> single web/dist/index.html
python web/scripts/gen_sample.py                           # refresh browser dev sample after contract changes

# Desktop app (Windows; run from repo root)
pip install -r desktop/requirements.txt
python -m desktop.shell
```
- **CI** (`.github/workflows/tests.yml`): pytest on ubuntu + windows-latest, plus svelte-check + vite build. Must stay green.
- **Windows `.exe`**: `package-windows.yml` builds it on every push (paths `desktop/**`,`core/**`,`web/**`); download the `PQA-windows-x64` artifact from the latest green run.
- **Headless visual check** (Linux/CI): serve/load `web/dist/index.html` in Chromium (Playwright) and screenshot — works because the build is a single file and the MockBackend serves committed sample data.

## Verification expectations for each change
- `pytest tests/` green (parity numbers unchanged unless deliberately regenerated via `tests/generate_golden.py`).
- `npm run check` 0 errors; `npm run build` succeeds.
- New backend methods covered by a test; new contract fields stay JSON-serialisable.

## Platform notes (Windows on ARM / Parallels)
- WebView2 runtime ships with Windows 11. pywebview's WebView2 backend loads via
  **.NET + WinForms**, which is **not** installed by the pip wheels. On normal x64
  Windows the built-in .NET Framework is used automatically; on **ARM64** you must
  ensure a WinForms-capable runtime. Known-good lever: set
  **`PYTHONNET_RUNTIME=netfx`** before pywebview is imported (uses the built-in
  .NET Framework 4.8.1, which includes WinForms). **TODO:** bake
  `os.environ.setdefault("PYTHONNET_RUNTIME","netfx")` into `desktop/shell.py` on
  Windows, and have the M5 installer provision the .NET Desktop Runtime.

## Conventions
- Commit messages end with the Co-Authored-By + Claude-Session trailers (see existing commits).
- Keep the PR a **draft**; never push to `main`.
- `core/` must stay pure (no host-only imports in the CSV/compliance path) for the future Pyodide path.
- Update this file's **Status** section as milestones complete.
