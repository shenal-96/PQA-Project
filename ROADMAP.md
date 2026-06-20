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
desktop/   shell.py (PyWebview + HostBridge) · report_host.py (build_report + Chromium PDF) ·
           viz_report.py (matplotlib report images) · xls_host.py (WinScope/SetPoint/ECU) ·
           pqa.spec (PyInstaller) · requirements.txt
tests/     parity harness (golden) + snapshot/recalc/contract/hostbridge tests
docs/      adr/0001 · run-windows-parallels.md
.github/workflows/  tests.yml (pytest matrix + web build) · package-windows.yml (.exe artifact)
visualizations.py · report.py · html_report.py · ecu_*.py · tracking.py  (host-native, kept at root)
```

## Status by milestone
- **M0 ✅** Monorepo scaffold, engine → `core/`, backend seam + JSON contract, deps rewrite (`desktop/requirements.txt`).
- **M1 ✅** PyWebview shell + `HostBridge` (load_csv/run_analysis/metric_series), first ECharts chart + events table, **parity harness** (golden numbers, CI).
- **M2 ✅** Full **Compliance tab**: config sidebar (all `AnalysisConfig` fields), ISO 8528 presets, 6 metric charts, compliance table (pills/fault badge), **4-panel event snapshots**, **deferred streaming**, **per-event overrides + Recalculate** (`core/recalc.py`), Industrial-Precision design system.
- **M3 ✅ Reports** — host-side report builder: editable `.docx` (python-docx), self-contained **HTML**, and **PDF via headless Chromium/Edge** (`--headless=new --print-to-pdf`, no LibreOffice/WeasyPrint); hi-DPI matplotlib report images.
  - New: `desktop/viz_report.py` (wraps the validated `visualizations` renderers → `Graphs/Images/Snapshots` layout that `report.get_placeholder_map` scans) and `desktop/report_host.py` (`find_chromium`, `html_to_pdf`, `build_report`, default template, filename sanitising, leftover-placeholder cleanup).
  - `HostBridge.generate_report` / `default_html_template` / `save_dialog` (native Save-As, Windows). PDF export is **folded into `generate_report`** (`outputs.pdf` → `report_host.html_to_pdf`) rather than a separate `export_pdf` bridge method.
  - Reports run host-side from the **cached** `df_proc`/`df_events` (engine output — and so they honour any Recalculate overrides), never re-derived in JS. Reuses `report.get_placeholder_map`/`inject_images_to_word` and `html_report.get_default_template`/`inject_html_placeholders` (used `inject_images_to_word` + `doc.save` directly so output lands in a temp dir, not cwd).
  - Frontend: `web/src/lib/ReportPanel.svelte` (fields form + PDF/HTML/.docx toggles + optional Word-template upload + download / native Save-As), gated on `caps.canReport`; backend seam gains `generateReport`/`defaultHtmlTemplate`/`saveFile?`. Mock backend reports `canReport:false` so the panel is discoverable-but-disabled in the browser preview.
  - Packaging fix: `pqa.spec` no longer **excludes** matplotlib (reports need it) and now bundles it + declares the lazily-string-imported `report`/`html_report`/`visualizations`/`docx`/`PIL` as hidden imports.
  - Tests: `tests/test_report.py` (31 total green). The Chromium subprocess wiring is covered with a fake browser; the **real Chromium/Edge render is Windows/Edge-verifiable** (confirmed locally against a Chromium build — valid multi-page PDF).
  - **Deferred to M5:** deleting the LibreOffice/WeasyPrint/reportlab PDF chains from `report.py`/`html_report.py` — the live Streamlit `app.py` still imports them; they're removed alongside `packages.txt`/dead-dep cleanup when `app.py` is retired. The desktop path already bypasses them entirely.
- **M4 ✅ Other tabs (host XLS via python_calamine)** — top-level tab nav (Compliance / WinScope / Set Point / ECU Plotting), XLS tabs gated on `caps.canXls`.
  - New `desktop/xls_host.py`: `load_winscope_df` (→ `analysis.load_winscope_xls`, tagged `logger_format="winscope"` so `run_analysis` sets `skip_interpolation=True`), `compare_setpoint` (XLS via `ecu_parser`+calamine / ComAp CSV via `ecu_csv_parser`, diffed by `ecu_multi_comparator`/`ecu_csv_comparator`), `load_ecu_recording_data` (`ecu_recording_parser` → grouped, humanised JSON series). `HostBridge.load_winscope`/`compare_setpoint`/`ecu_recording`.
  - `ecu_parser.parse_file` gained an optional `engine=` (desktop passes `"calamine"` → reads .xls/.xlsx without xlrd/openpyxl; default keeps legacy behaviour).
  - Frontend: `App.svelte` → tab shell with lazy-mount-then-hide views (state survives tab switches). `ComplianceView.svelte` (extracted, `mode='csv'|'winscope'`) so **WinScope reuses the whole Compliance UI**; `SetPointView.svelte` (toggle XLS/CSV, multi-file, filterable diff table + CSV export); `EcuPlotView.svelte` + `EcuChart.svelte` (per-group tabs + Custom Plot, channel toggle chips, multi-line ECharts with tidy labels). Backend seam + Mock samples (`sample_ecu.json`, `sample_setpoint.json`); Mock `canXls:true` so the browser preview demos all tabs.
  - **Deferred:** the "configure parameter groups" data-editor (channel reassignment) from the Streamlit ECU tab — current build auto-groups + Custom Plot covers the core need.
- **M5 🟡 Packaging & polish (installer done; destructive cleanup deferred)** — **the live Streamlit app stays untouched** (must keep running via `streamlit run app.py` until the desktop build is signed off; per owner instruction, do NOT modify `app.py`/`tracking.py`/`report.py`/`html_report.py`/`packages.txt`/root `requirements.txt`).
  - ✅ **Inno Setup installer** `desktop/installer.iss`: packages the PyInstaller onedir, silently provisions the **WebView2 Evergreen Runtime** if absent, and verifies **.NET Framework 4.8** (the app uses `PYTHONNET_RUNTIME=netfx` → built-in Framework/WinForms, so the modern .NET Desktop Runtime is **not** needed). `package-windows.yml` now compiles it via `choco install innosetup` and uploads **PQA-windows-installer** — so the `.iss` is compile-verified in CI. Runbook: `docs/build-windows-installer.md`.
  - ⏳ **Deferred until parity sign-off** (all touch the live Streamlit app): telemetry de-Streamlit (`tracking._get_secret` → env); remove dead deps + `packages.txt`; delete the LibreOffice/WeasyPrint/reportlab PDF chains from `report.py`/`html_report.py` (deferred from M3); flip `console=True`→`False` in `pqa.spec`; code-sign; retire `app.py`.
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
