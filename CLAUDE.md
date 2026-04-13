# PQA — Power Quality Analysis

Power quality compliance tool for the backup energy generation industry.
Processes CSV logger data, detects load events, calculates voltage/frequency
recovery times, and generates Word/PDF compliance reports (ISO 8528).

## Run

```bash
streamlit run app.py --server.port 8502
```

Logs to `/tmp/pqa_debug.log` (also printed to terminal).

## File Map

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI — upload, config, event review, export |
| `analysis.py` | Pure data functions — no UI deps. Entry point: `perform_analysis()` |
| `visualizations.py` | Matplotlib plots and snapshots — no UI deps |
| `report.py` | Word template injection + PDF conversion via LibreOffice |
| `html_report.py` | HTML template injection + PDF conversion (alternative pipeline) |
| `uploads/` | Persisted CSV and Word template uploads (survive reruns) |
| `output/` | Ephemeral per-run artefacts (Graphs/, Snapshots/, Images/, Template/) |

## Architecture

- `analysis.py` is UI-free. Keep it that way — no `st.*` imports.
- `visualizations.py` is UI-free. Keep it that way.
- `html_report.py` is UI-free. Keep it that way.
- `app.py` calls `_recompute_df_interp(df_proc)` when it needs the interpolated
  frame outside of `perform_analysis` (e.g. after override recalculation).
  This function must stay in sync with the interpolation logic in `perform_analysis`.

## Key Decisions

### df_interp — compliance uses 100 ms interpolated data
Raw CSV is ~1 s/sample. Recovery times and peak deviations are measured on
`df_interp` (100 ms linear interpolation). **df_interp is never used for
plots or snapshot displays** — only for numeric compliance calculations.

### detection_window_s (default 5 s)
Load-step events within this window are merged into one grouped event.
Prevents double-counting ramp-style load changes.

### Recovery requires 0.3 s sustained in-band
`calculate_recovery_time` requires `sustain_s=0.3` (3 consecutive 100 ms
points) all within the band before declaring recovery. Prevents declaring
recovery on a brief transient re-entry.

### Asymmetric frequency recovery bands
Load increase (dKw > 0): freq drops → band `[49.75, 50.50]` Hz  
Load decrease (dKw ≤ 0): freq rises → band `[49.50, 50.25]` Hz  
Rationale: generator governor response is asymmetric; ISO 8528 recovery
tolerance is not simply ±0.5 Hz around nominal.

### Voltage: L-N columns scaled to L-L
If logger provides `U1/U2/U3_rms_AVG` (line-to-neutral), multiply average
by √3 to get `Avg_Voltage_LL`. Compliance is always checked against L-L.
`U_avg_AVG` (ROMP4 format) is treated directly as L-L.

### PDF conversion — two parallel pipelines

**Word Template pipeline (report.py):**
1. LibreOffice headless (preferred — installed via `packages.txt` on Cloud)
2. WeasyPrint fallback (lower fidelity, needs cairo/pango system libs)
3. fpdf2 last resort (plain text dump)
Converter that succeeds is logged: "PDF conversion succeeded via try_libreoffice"

**HTML Template pipeline (html_report.py):**
1. WeasyPrint (best for Cloud — cairo/pango in packages.txt)
2. LibreOffice headless (converts HTML directly — good local option)
3. reportlab (pure Python fallback — functional layout, no system deps)
Images are embedded as base64 in the HTML, so the .html file is fully self-contained.

**Local Mac PDF fix:** `brew install --cask libreoffice` — covers both pipelines.

### Report format toggle
`st.session_state["report_format"]` holds "Word Template" or "HTML Template".
`st.session_state["html_template"]` holds the editable HTML string (persists across
reruns). Reset button restores `get_default_template()` from `html_report.py`.
Generated report entries store files under keys: "docx", "html", "pdf".

### AnalysisConfig
All parameters live in `AnalysisConfig` (dataclass). `iso_8528_defaults()`
returns the standard preset. UI sliders write directly to this config object
before calling `perform_analysis`.

## Deploy Target

**Streamlit Cloud.** `packages.txt` installs system packages including
`libreoffice` for PDF export. Do not remove it.
`requirements.txt` includes `reportlab>=4.0.4` for the HTML pipeline fallback.

## Conventions

- Functions in `analysis.py`, `visualizations.py`, `html_report.py` accept and
  return plain Python/pandas/numpy — no Streamlit session state.
- Streamlit widget keys follow `"snake_case_{idx}"` pattern for per-event
  controls. Keep keys unique or reruns will conflict.
- `output/` dirs are wiped and recreated on each analysis run (`init_output_dirs`).
  Do not write anything there that needs to persist across runs.
- Use `pd.to_numeric(..., errors="coerce")` before any arithmetic on CSV
  columns — logger data frequently contains null strings.

## Known Gotchas

- **Do not restart Streamlit** to pick up code changes when running locally;
  use the browser "Rerun" button or `st.rerun()` in code. A full restart loses
  `st.session_state` and breaks the override workflow.
- `calculate_exit_time` scans *backwards* from the event timestamp. If the
  signal was out-of-band for the entire 30 s lookback, it returns `None` —
  this is intentional (can't determine when the excursion began).
- The `intersection_overrides` session-state dict is keyed by event integer
  index from `df_events`. If events are re-detected (new config), clear or
  reinitialise overrides to avoid stale keys mapping to wrong events.
- LibreOffice conversion spawns a subprocess with a 90 s timeout. On Streamlit
  Cloud cold starts this can feel slow — expected behaviour.
- `packages.txt` pango/cairo entries are required for WeasyPrint to render
  fonts correctly even when LibreOffice is the primary PDF path.
- HTML template `text_area` widget key is `"html_template_editor"`. The value
  is synced to `st.session_state["html_template"]` on every rerun. Do not
  drive both from the same key or Streamlit will raise a duplicate widget error.
- WeasyPrint imports will fail on local Mac without `brew install cairo pango
  gobject-introspection` — this is expected. LibreOffice and reportlab are the
  fallbacks and require no extra system packages (beyond LibreOffice itself).
