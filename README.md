# PQA — Power Quality Analysis (Desktop)

Fully-local **Windows desktop app** for power-quality compliance analysis (ISO 8528):
CSV/XLS logger ingest, load-event detection, voltage/frequency recovery times, and
Word/PDF compliance reports. The UI is a Svelte/ECharts front-end rendered in an
embedded Edge **WebView2** control via **PyWebview** — 100% local, no server, ships
as a single PyInstaller `.exe`.

> **The legacy Streamlit app lives on the [`streamlit-legacy`](https://github.com/shenal-96/PQA-Project/tree/streamlit-legacy) branch.**
> `main` is now the desktop app. The two share the validated analysis engine
> (`core/analysis.py`); engine changes are ported between branches as needed.

## Run / build

```bash
# Engine + bridge tests (the parity harness is the central correctness guard)
pip install "pandas>=2.2,<3" "numpy>=1.24" pytest
python -m pytest tests/ -q

# Web UI (single self-contained web/dist/index.html)
cd web && npm install && npm run build && npm run check

# Desktop app (Windows; from repo root)
pip install -r desktop/requirements.txt
python -m desktop.shell
```

The Windows `.exe` + Inno Setup installer build in CI on every push
(`.github/workflows/package-windows.yml` → `PQA-windows-x64` / `PQA-windows-installer`).

## Layout

| Path | Purpose |
|---|---|
| `core/` | Pure pandas/numpy engine (`analysis.py`), JSON contract (`serialize.py`), chart/snapshot data-prep (`viz_dataprep.py`), recalc (`recalc.py`) |
| `desktop/` | PyWebview shell + `HostBridge` (`shell.py`), reports (`report_host.py`, `viz_report.py`), XLS tabs (`xls_host.py`), PyInstaller spec, Inno Setup installer |
| `web/` | Svelte + Vite + ECharts UI; `src/backend/` adapter seam (PyWebview now, Pyodide/iPad later) |
| `tests/` | Parity harness (golden), contract/host-bridge/snapshot/recalc/report/XLS tests |
| `visualizations.py`, `report.py`, `html_report.py`, `ecu_*.py` | Host-native modules reused by the desktop (and the Streamlit app on `streamlit-legacy`) |

See **`ROADMAP.md`** for the architecture and milestone status, and **`CLAUDE.md`** for
domain/engine reference (compliance logic, logger formats, recovery algorithm).
