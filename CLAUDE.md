# PQA — Power Quality Analysis

Power quality compliance tool for the backup energy generation industry.
Processes CSV logger data, detects load events, calculates voltage/frequency
recovery times, and generates Word/PDF compliance reports (ISO 8528).

## Run

```bash
streamlit run app.py --server.port 8502
```

For remote access from another device:
```bash
streamlit run app.py --server.port 8502 --server.address 0.0.0.0
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
| `uploads/dev_settings.json` | Dev mode persisted sidebar settings (survive restarts) |
| `output/` | Ephemeral per-run artefacts (Graphs/, Snapshots/, Images/, Template/) |

## Architecture

- `analysis.py` is UI-free. Keep it that way — no `st.*` imports.
- `visualizations.py` is UI-free. Keep it that way.
- `html_report.py` is UI-free. Keep it that way.
- `app.py` calls `_recompute_df_interp(df_proc)` when it needs the interpolated
  frame outside of `perform_analysis` (e.g. after override recalculation).
  This function must stay in sync with the interpolation logic in `perform_analysis`.
- All paths are pinned to the script directory via
  `_APP_DIR = os.path.dirname(os.path.abspath(__file__))` in `app.py`.
  This ensures uploads and output dirs resolve correctly regardless of the
  working directory from which Streamlit is launched.

## Key Decisions

### df_interp — compliance uses 100 ms interpolated data
Raw CSV is ~1 s/sample. Recovery times are measured on `df_interp`
(100 ms linear interpolation). **df_interp is never used for plots,
snapshot displays, or deviation values** — only for recovery/exit time
calculations.

### V_dev / F_dev — actual measured extreme, not signed deviation
`V_dev` holds the actual measured voltage (V), `F_dev` the actual measured
frequency (Hz), taken from `df_proc` (raw measured data only):
- Load increase (dKw > 0): signal drops → store `vals.min()`
- Load decrease (dKw ≤ 0): signal rises → store `vals.max()`

Compliance check: `abs(V_dev - nom_v) / nom_v * 100`
Display format: `"406.2 V (-2.12%)"` — the actual value plus its % deviation.
This is implemented in `_measured_extreme()` in `analysis.py`.

### detection_window_s (default 5 s)
Load-step events within this window are merged into one grouped event.
Prevents double-counting ramp-style load changes.

### snapshot_window_s (default 10 s, user-configurable 3–60 s)
The time window used both for snapshot plots (±window_s around the event)
and for the `_measured_extreme` lookup. Keeping both in sync means the
table value always reflects exactly what the snapshot shows.

### Recovery requires sustained in-band with oscillation handling
`calculate_recovery_time` uses a candidate-invalidation approach: when a
sustained in-band window (sustain_s=0.3, 3 consecutive 100 ms points) is
found, it is recorded as a *candidate* and verification continues for
verify_s=10.0 seconds. If the signal exits the band again during that
verification window (oscillation), the candidate is discarded and the
search resumes. This correctly handles waveforms that oscillate in and
out of the recovery band before final settlement, without being
affected by subsequent unrelated load events.

### Asymmetric frequency recovery bands
Load increase (dKw > 0): freq drops → band `[49.75, 50.50]` Hz
Load decrease (dKw ≤ 0): freq rises → band `[49.50, 50.25]` Hz
Rationale: generator governor response is asymmetric; ISO 8528 recovery
tolerance is not simply ±0.5 Hz around nominal.

### Multi-voltage support
`nom_v` is configurable in the sidebar (415 V, 690 V, 11000 V presets or
custom input). The `AnalysisConfig.nominal_voltage` field carries this into
analysis. All compliance checks and display formatting are relative to the
configured nominal.

### Voltage: L-N columns scaled to L-L
Controlled by `AnalysisConfig.ln_to_ll_mode`:
- `"auto"` — detect by column name: `U1/U2/U3_rms_AVG` = L-N (×√3), `U12/U23/U31_rms_AVG` = L-L
- `"force_ll"` — treat all voltage columns as L-L (no scaling)
- `"force_ln"` — treat all voltage columns as L-N (×√3 applied)
`U_avg_AVG` (ROMP4 format) is treated directly as L-L.
Compliance is always checked against L-L.

### Recovery time calculation
**`calculate_exit_time(df_interp, event_ts, col, upper, lower)`** — scans
backwards from event timestamp to find the exact moment the signal crossed
out of band (linear interpolation between last in-band / first out-of-band
points). Returns `None` if the signal was in-band at the event time (no
excursion) or out of band for the entire 30 s lookback.

### Not-recovered detection
After computing exit/recovery times, `perform_analysis` checks whether the
signal was already out of band at each event's timestamp. If so, the event
gets `V_not_recovered=True` or `F_not_recovered=True`. The snapshot expands
its time window to show exit and recovery markers from the previous event,
the affected panel gets a red tint with a watermark, and the event expander
in the UI shows a warning banner.

**`calculate_recovery_time(df_interp, start_ts, col, upper, lower)`** — scans
forward from `start_ts`, finds first sustained in-band window (0.3 s), linearly
interpolates exact re-entry crossing.

**Recovery time = exit crossing → re-entry crossing** (not load-change → re-entry).
Recovery is only calculated and checked when `V_exit_ts` / `F_exit_ts` is non-null.

### PDF conversion — two parallel pipelines

**Word Template pipeline (report.py):**
1. LibreOffice headless (preferred — installed via `packages.txt` on Cloud)
2. WeasyPrint fallback (lower fidelity, needs cairo/pango system libs)
3. fpdf2 last resort (plain text dump)

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

### Dev Mode — persist sidebar settings
A "🛠 Dev Mode" expander at the top of the sidebar saves all sidebar selections
(checkboxes, sliders, nominal voltage, load threshold, freq bands, etc.) to
`uploads/dev_settings.json` on every Run Analysis. On cold start, the loader
pre-populates `st.session_state` from this file before widgets are rendered.
**Important:** keyed widgets must NOT also have a `value=` argument — Streamlit
raises a duplicate-key conflict. Only pre-populate via `session_state`.

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

## Design Tokens (visualizations.py)

```python
_NAVY   = "#0f172a"   _BLUE   = "#2563eb"   _GREEN  = "#16a34a"
_RED    = "#dc2626"   _ORANGE = "#ea580c"   _CYAN   = "#0891b2"
_PURPLE = "#9333ea"   _AMBER  = "#f59e0b"   _LIME   = "#10b981"
_GRID   = "#e2e8f0"   _TEXT_MAIN = "#0f172a"  _TEXT_SUB = "#64748b"
_BG     = "#ffffff"
```

Fonts: Inter (UI) + JetBrains Mono (data/inputs). Sidebar: deep navy `#0f172a`.
Main time-series plots use `%H:%M:%S` time format on the x-axis.

## UI Design System (app.py)

Direction: **Industrial Precision** — authoritative, data-forward, dark sidebar with light main area.

### App-level CSS classes (injected via `st.markdown`)

| Class | Purpose |
|---|---|
| `.pqa-metrics` | Flex container for the 5-card metric strip after Run Analysis |
| `.pqa-metric-card` | Individual metric card (dark gradient, border-radius 10px) |
| `.pqa-metric-card.pass` | Green border + green value text |
| `.pqa-metric-card.fail` | Red border + red value text |
| `.pqa-metric-card.overall-pass/.overall-fail` | 2px accent border for the result card |
| `.pqa-overall-badge` | Pill badge inside result card (ALL PASS / N FAILS) |
| `.pqa-section-header` | Flex row: coloured accent bar + title + optional badge |
| `.pqa-section-bar` | 4×22px coloured vertical bar (blue=compliance, cyan=plots, purple=snapshots) |
| `.pqa-section-badge` | Pill badge on section headers (green=all pass, red=failures) |

### Section accent colours

| Section | Bar colour |
|---|---|
| Compliance Results | `#2563eb` (blue) |
| Time-Series Plots | `#0891b2` (cyan) |
| Event Snapshots | `#9333ea` (purple) |

### Key UI components

- **Sidebar header** — custom HTML with SVG icon + "CONFIGURATION" label (no `st.title()`)
- **App title** — custom HTML card with bolt SVG icon, bold heading, subtitle tagline
- **Empty state** — dashed-border centred card with bolt icon (replaces plain `st.info()`)
- **Post-analysis metrics** — 5-card HTML strip rendered via `st.markdown`; replaces `st.metric()` calls so pass/fail can be colour-coded
- **Compliance table** — rendered via `_render_compliance_html()` with pill Pass/Fail badges, red row tint on fail rows, rounded table corners
- **Tabs** — underline style (blue 2px border-bottom on active, no filled background)
- **Expanders** — hover lift, open-state header border, `h_pad` transition

## Debug Overlay (`show_debug=True` in `generate_plots()`)

| Element | Colour | Meaning |
|---|---|---|
| Vertical `⋯` line | Amber | Load-change detection timestamp |
| `±thresh_kw` horizontal lines + dKw labels | Amber | On kW graph |
| Vertical `⋯` + orange ★ | Orange | Exact V/F **exit** crossing |
| Vertical `⋯` + lime ★ + time label | Lime | Exact V/F **re-entry** crossing |
| Asymmetric dotted band lines | Amber | Per-event frequency bounds (F graph) |

Band boundary marker selection: `v_dev > nom_v` → upper band (voltage rose);
otherwise lower band (voltage dropped). Same logic for frequency.

## Known Gotchas

- **Do not restart Streamlit** to pick up code changes when running locally;
  use the browser "Rerun" button or `st.rerun()` in code. A full restart loses
  `st.session_state` and breaks the override workflow.
  **Exception:** changes to `analysis.py`, `visualizations.py`, or `report.py`
  require a full restart — hot-reload only applies to `app.py`.
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
- `st.dataframe` uses `width='stretch'` — **not** `use_container_width=True`
  (Streamlit version quirk).
- `shutil.rmtree` on macOS may fail with `OSError: Directory not empty` due to
  `.DS_Store` files — use `ignore_errors=True` in `init_output_dirs`.
- CSV upload does **not** call `st.rerun()` after saving — files appear in the
  dropdown on the next natural rerun. Forcing a rerun caused remote browsers to
  not refresh correctly.
