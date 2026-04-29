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
| `ecu_parser.py` | XLS/XLSX ECU parameter file parser (Parameter, Val_2D, Val_3D sheets) |
| `ecu_csv_parser.py` | ComAp CSV configuration file parser (semicolon-delimited, Group/Sub-group/Name/Value) |
| `ecu_multi_comparator.py` | Multi-file XLS/XLSX diff engine — finds all locations where values differ |
| `ecu_csv_comparator.py` | Multi-file CSV diff engine — finds all parameter differences |
| `uploads/` | Persisted CSV and Word template uploads (survive reruns) |
| `uploads/dev_settings.json` | Dev mode persisted sidebar settings (survive restarts) |
| `output/` | Ephemeral per-run artefacts (Graphs/, Snapshots/, Images/, Template/) |

## Top-Level Tabs

The app uses a horizontal `st.radio` as a tab selector (`_TAB_LABELS` / `_TAB_KEYS` in app.py). Adding a new tab requires both lists and an `elif _active_tab_main == "<key>":` block.

| Label | Key | Purpose |
|---|---|---|
| ⚡ Compliance Analysis | `compliance` | Main PQA workflow — CSV upload, analysis config, results, report generation |
| 📊 WinScope Viewer | `winscope` | High-resolution WinScope XLS data viewer with compliance analysis |
| 🔧 Set Point Comparison | `setpoint` | ECU parameter file comparator — diff XLS/XLSX/CSV files across multiple units |

### Set Point Comparison tab
Imports `ecu_parser`, `ecu_csv_parser`, `ecu_multi_comparator`, `ecu_csv_comparator` lazily inside the `elif` block (no startup cost on other tabs). Three inner sub-tabs: XLS Comparison / XLSX Comparison / CSV Comparison. Results shown as a filterable dataframe with CSV download.

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
The **total** time span shown in snapshot plots. The event sits at t=0,
and the plot spans [-window_s/2, +window_s/2]. Also controls the
`_measured_extreme` lookup window so the table value matches what the
snapshot shows. The x-axis is in relative seconds ("Time relative to event").

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

### Asymmetric max-deviation display in snapshots
`plot_load_change_snapshot()` draws **only the relevant** max-deviation
limit line (red dashed) per event:
- Load increase (dKw > 0) → voltage/freq drops → only the **lower** limit
- Load decrease (dKw ≤ 0) → voltage/freq rises → only the **upper** limit

The legend entry for the deviation limit follows the same rule. This
matches `check_compliance()` in `analysis.py`, which has always picked
the direction-appropriate limit for evaluation; the snapshot display is
now consistent with the evaluation.

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
| `.pqa-metrics` | CSS Grid container (`auto-fit, minmax(160px, 1fr)`) for the 5-card metric strip — uniform column widths, wraps to a 2nd row on narrow windows |
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

### Responsive layout

- `.main .block-container` has `max-width: 100%` with fluid horizontal
  padding (`clamp(1rem, 3vw, 3rem)`) — the app stretches to fill any
  window width instead of being capped at 1240px.
- Metric value font-size, section title font-size, and metric-card
  padding all use `clamp()` for fluid scaling.
- Compliance / WinScope tab order: Time-Series Plots → Compliance
  Results → (Temperatures & Pressures, WinScope only) → Event Snapshots.
  Time-Series moved above the table so the highest-signal visual lands
  first on the page.

### Compliance table HTML embed (`_render_compliance_html`)

- Headers wrap (`white-space: normal`, `word-break: break-word`,
  `vertical-align: bottom`) so the rightmost column is never cropped at
  narrow widths.
- Event Time column uses `<br>` between start and end timestamps
  (formatted in `_fmt_ts` / `_ws_fmt_ts`); the cell does not have
  `white-space: nowrap`.
- Iframe height = `54 + len(rows) * 66` plus `+22` per `<br>` in the
  Failure Reasons column. Tuned for the 2-line cells in the deviation
  columns; do not raise unnecessarily.

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

## Snapshot Toggles (sidebar → Snapshot Display Options)

| Toggle | Effect on `plot_load_change_snapshot()` |
|---|---|
| Show Tolerance Band on Snapshots | Amber dashed lines at the recovery band |
| Show Deviation Limits on Snapshots | Red dashed line — only the direction-relevant max-dev limit |
| Show Intersection Points | Orange ★ at exit, lime ★ at recovery, plus vertical guide lines |
| Show Max Deviation | Red ★ at the V/F extreme within the 5 s post-event window — value matches the V_dev / F_dev in the compliance table. Marker is placed using `Avg_Voltage_LL` / `Avg_Frequency` (idxmin on increase, idxmax on decrease) so it lands on the same point analysis used. Adds a `Max Deviation (xx V/Hz)` legend entry. |

## Preset Configurator (in progress — 2026-04-29)

### Goal
Replace the three hardcoded ISO preset checkboxes with a configurable preset system. Users can edit existing presets, create new ones, and select presets via a dropdown. Preset data is persisted in `uploads/presets.json` so it survives app restarts.

### New file: `uploads/presets.json`
Stores presets as a JSON array of dicts. If the file is absent, `_load_presets()` seeds it from `_BUILTIN_PRESETS`. The file lives in `uploads/` so it is never cleared by `init_output_dirs()`.

Each preset dict keys:
```
name, v_tol, v_rec, v_max_dev_inc, v_max_dev_dec,
f_tol, f_rec, f_max_dev_inc, f_max_dev_dec,
f_rec_upper_inc, f_rec_lower_inc, f_rec_upper_dec, f_rec_lower_dec,
apply_asymmetric_freq, apply_asymmetric_volt,
apply_asymmetric_volt_dev, apply_asymmetric_freq_dev
```

Built-in seeds:
| Name | v_tol | v_rec | v_max_dev_inc/dec | f_tol | f_rec | f_max_dev_inc/dec | freq bands (inc upper/lower / dec upper/lower) |
|---|---|---|---|---|---|---|---|
| ISO 8528 G3 | 1.0 | 4.0 | 15/20 | 0.5 | 3.0 | 7/10 | 50.50/49.75 / 50.25/49.50 |
| ISO 8528 G2 | 5.0 | 6.0 | 20/25 | 0.5 | 5.0 | 10/12 | 51.50/48.75 / 51.25/48.50 |
| ISO 8528 G1 | 10.0 | 10.0 | 25/30 | 0.5 | 10.0 | 15/18 | 51.50/48.75 / 51.25/48.50 |
All built-ins: `apply_asymmetric_freq=True`, `apply_asymmetric_volt=False`, `apply_asymmetric_volt_dev=True`, `apply_asymmetric_freq_dev=True`.

### app.py changes

**Constants & helpers** (near `DEV_SETTINGS_FILE`):
- `_PRESETS_FILE = "uploads/presets.json"`
- `_BUILTIN_PRESETS: list[dict]` — hardcoded fallback (3 presets)
- `_load_presets() -> list[dict]` — reads file; seeds from `_BUILTIN_PRESETS` + writes if missing
- `_save_presets(presets: list[dict]) -> None` — writes to `_PRESETS_FILE`

**`_DEV_DEFAULTS`**:
- Remove: `"apply_iso"`, `"apply_iso_g2"`, `"apply_iso_g1"`
- Add: `"active_preset": "None"`

**Session state init** (once, before sidebar renders):
```python
if "presets" not in st.session_state:
    st.session_state["presets"] = _load_presets()
```

**Sidebar UI** (replaces lines 1328–1341 — the 3 checkboxes + mutual-exclusivity block):
```python
if st.button("⚙ Configure Presets", use_container_width=True):
    _configure_presets_dialog()
_preset_names = ["None"] + [p["name"] for p in st.session_state["presets"]]
active_preset = st.selectbox("Active Preset", _preset_names,
    index=_preset_names.index(_ds.get("active_preset", "None"))
    if _ds.get("active_preset", "None") in _preset_names else 0,
    key="active_preset_select")
```

**Dialog** (new decorated function, defined before `_configure_presets_dialog()` call site):
```python
@st.dialog("Configure Presets", width="large")
def _configure_presets_dialog():
    # st.data_editor with num_rows="dynamic", full column_config for all 17 keys
    # "Save Presets" button → _save_presets() + st.session_state["presets"] = ... + st.rerun()
```

**`_any_preset` variable** (line ~1410):
- Old: `apply_iso or apply_g2 or apply_g1`
- New: `active_preset != "None"`

**Preset application block** (replaces lines 1437–1481):
- Look up preset by name in `st.session_state["presets"]`
- Apply all 17 fields from the dict; set the 4 asymmetric flags in `_ds`

**`_ds` save block** (lines 1407–1410):
- Remove the three `_ds["apply_iso*"]` lines
- Add: `_ds["active_preset"] = active_preset`

### Implementation tasks (sequential)
1. **Foundation** — Create `presets.json`, add `_PRESETS_FILE` + `_BUILTIN_PRESETS` + `_load_presets()` + `_save_presets()`, update `_DEV_DEFAULTS`, init session state.
2. **UI** — Add `_configure_presets_dialog()` dialog function, replace 3 checkboxes with button + selectbox, remove mutual-exclusivity logic.
3. **Logic** — Replace hardcoded preset application block with dynamic lookup, update `_ds` save block, fix `_any_preset` calculation.

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
