# PQA — Power Quality Analysis

> **⚠️ Branch note:** `main` is now the **desktop app** (PyWebview/WebView2 + Svelte).
> The document below describes the **legacy Streamlit app**, which now lives on the
> **`streamlit-legacy`** branch. It is kept here because the desktop app reuses the
> same validated analysis engine and host modules (`core/analysis.py`,
> `visualizations.py`, `report.py`, `html_report.py`, `ecu_*.py`), so the
> **domain/engine sections remain accurate and useful** (compliance logic, Hioki/Miro
> formats, recovery algorithm, ISO bands). The Streamlit-UI sections (`app.py`,
> `st.*`, tabs) apply only to `streamlit-legacy`. **For the desktop architecture and
> milestone status, see `ROADMAP.md`.**

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
| `ecu_recording_parser.py` | XLS/XLSX time-series ECU recording parser + keyword-based channel grouping (Temperatures, Pressures, Speeds, Power, Electrical, Fuel/Flow, Levels, Other) |
| `tracking.py` | Telemetry — usage events, error logs, crash reports → Google Sheets webhook (silent-fail, daemon thread) |
| `uploads/` | Persisted CSV and Word template uploads (survive reruns) |
| `uploads/dev_settings.json` | Dev mode persisted sidebar settings (survive restarts) |
| `output/<session_id>/` | Ephemeral per-run artefacts (Graphs/, Snapshots/, Images/, Template/) — session-scoped per browser tab so concurrent tabs do not wipe each other's plots/snapshots when `init_output_dirs()` runs |

## Top-Level Tabs

The app uses a horizontal `st.radio` as a tab selector (`_TAB_LABELS` / `_TAB_KEYS` in app.py). Adding a new tab requires both lists and an `elif _active_tab_main == "<key>":` block.

| Label | Key | Purpose |
|---|---|---|
| ⚡ Compliance Analysis | `compliance` | Main PQA workflow — CSV upload, analysis config, results, report generation |
| 📊 WinScope Viewer | `winscope` | High-resolution WinScope XLS data viewer with compliance analysis |
| 🔧 Set Point Comparison | `setpoint` | ECU parameter file comparator — diff XLS/XLSX/CSV files across multiple units |
| 🔌 ECU Plotting | `ecu_plotting` | Time-series viewer for ECU recordings (XLS/XLSX) — auto-grouped channels, per-plot dataset selection, no compliance analysis |

### Set Point Comparison tab
Imports `ecu_parser`, `ecu_csv_parser`, `ecu_multi_comparator`, `ecu_csv_comparator` lazily inside the `elif` block (no startup cost on other tabs). Three inner sub-tabs: XLS Comparison / XLSX Comparison / CSV Comparison. Results shown as a filterable dataframe with CSV download.

### ECU Plotting tab
Imports `ecu_recording_parser` and `visualizations.plot_ecu_group` lazily inside the `elif` block. Uploads land in `UPLOADS_ECU_RECORDING_DIR = uploads/ecu_recording/{SESSION_ID}/`; plots are written to `output/{SESSION_ID}/ECU/` (NOT wiped by `init_output_dirs()` because ECU plotting is independent of the compliance Run Analysis flow). XLS/XLSX is read via `python_calamine` (xlrd fails on vendor-exported XLS like the test file with strange country/locale codes); the parser auto-picks the first non-empty sheet and auto-detects a timestamp column with strong/weak hint matching (strong: `datetime`/`timestamp`/`pc time`; weak: `date`/`time` plus value-parseability check, so an elapsed-seconds column like `TIME_§s` is not mistaken for the timestamp). Vendor-specific datetime formats (e.g. `2026-04-18 12:32:02,623000us`) are normalised by stripping the `us` suffix and swapping the comma for a dot. Channels are auto-classified by name keyword (Temperatures / Pressures / Speeds / Power / Electrical / Fuel/Flow / Levels / Other) and rendered as one tab per group plus a `🎯 Custom Plot` tab; each tab has a multiselect to add/remove individual datasets. A "Configure parameter groups" expander uses `st.data_editor` to let the user reassign channels between groups. Raw vendor column names like `1__1_2500_044_Engine_Speed__ECU__§rpm` are humanised to `Engine Speed ECU (rpm)` via `_tidy_channel_label` for the multiselect labels and the plot legend (the data lookup still uses raw names).

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
Raw Hioki/generic CSV is ~1 s/sample. Recovery times are measured on
`df_interp` (100 ms linear interpolation). **df_interp is never used for
plots, snapshot displays, or deviation values** — only for recovery/exit
time calculations.

For Miro CSVs the interpolation is **always skipped** (`config.skip_interpolation = True`)
and `df_interp = df_proc.copy()` — see *Miro logger support* below for why.
The compliance Run Analysis path detects this from `df_raw.attrs["logger_format"]`
and sets the flag before calling `perform_analysis`. The "Recalculate Compliance"
override path threads the same flag through `_recompute_df_interp(df_proc, skip_interpolation=...)`
so a re-run matches the original.

### V_dev / F_dev — actual measured extreme, not signed deviation
`V_dev` holds the actual measured voltage (V), `F_dev` the actual measured
frequency (Hz), taken from `df_proc` (raw measured data only):
- Load increase (dKw > 0): signal drops → store `vals.min()`
- Load decrease (dKw ≤ 0): signal rises → store `vals.max()`

Compliance check: `abs(V_dev - nom_v) / nom_v * 100`
Display format: `"406.2 V (-2.12%)"` — the actual value plus its % deviation.
This is implemented in `_measured_extreme()` in `analysis.py`.

### detection_window_s (default 8 s) — algebraic-sum merging
All raw above-threshold rows within `detection_window_s` of the group's
`Start_Timestamp` are merged into one event by **algebraic sum**, regardless
of sign. Internal ramp oscillations (e.g. `+1255, -152, +390, -45, +602`)
collapse into a single net step instead of fragmenting into multiple events
with opposing directions. Groups whose merged net |dKw| ends up below
`load_threshold_kw` are dropped post-merge — that pattern is pure oscillation
around a stable load.

**Important regression caveat:** the pre-2026-05-05 logic also required
`same_direction` for merging. That check was removed because it was splitting
real block-load ramps on high-resolution data into 5–7 sub-events. If the user
has a deliberate test pattern that fires an UP step and a DOWN step within
`detection_window_s` of each other, those will now merge into one net event.
The remedy is to lower `detection_window_s` for that test, not to reinstate
the same-direction check (which breaks ramps). See `analysis.py` ~lines 728–755.

### snapshot_window_s (default 10 s, user-configurable 3–60 s)
The **total** time span shown in snapshot plots. The event sits at t=0,
and the plot spans [-window_s/2, +window_s/2]. Also controls the
`_measured_extreme` lookup window so the table value matches what the
snapshot shows. The x-axis is in relative seconds ("Time relative to event").

### Recovery requires sustained in-band with oscillation handling
`calculate_recovery_time` uses a candidate-invalidation approach: when a
sustained in-band window (`sustain_s=0.3`) is found, it is recorded as a
*candidate* and verification continues for `verify_s` seconds (default 10).
If the signal exits the band again during that verification window
(oscillation), the candidate is discarded and the search resumes. This
correctly handles waveforms that oscillate in and out of the recovery band
before final settlement, without being affected by subsequent unrelated
load events.

**Sample-rate-aware sustain/verify counts.** `sustain_pts` and `verify_pts`
are derived from `np.median(np.diff(timestamps))` rather than a hardcoded
0.1 s grid. Hioki interpolated data → 3 / 100 points (0.3 s / 10 s on a
100 ms grid). Miro at 1 s → 1 / 10 points. Miro at 200 ms → 2 / 50 points.
Hardcoding `int(sustain_s / 0.1)` (the pre-2026-05-05 form) was producing
100 s verify windows on 1 s Miro data, which is what made every event report
recovery times of 480–660 s and fail. See `analysis.py:calculate_recovery_time`
~lines 335–352.

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

### Steady-state analysis (ISO 8528-5 δ bands) — separate from transient
Opt-in (`AnalysisConfig.steady_state_enabled`, default False). Evaluates whether
the generator holds voltage/frequency inside the **tight δ tolerance bands**
(δU ±2.5%, δf ±2.0% by default — ISO 8528-5 Table 4) during **stable loaded
operation**, i.e. the dwell periods *between* load steps. **Only meaningful for
staged load-bank tests** (25/50/75/100% held for a dwell), so it is gated per
test/CSV.

**Do not mix bands:** steady-state uses the **δ** bands; transient analysis uses
the wider **α** (recovery target) / **β** (departure trigger) bands. The engine
keeps them separate — steady-state never touches the `*_recovery_*` fields.

Engine (`core/analysis.py`, all UI-free):
- `detect_steady_windows(df_proc, df_events, config)` — segments the record into
  dwell windows = spans *between* consecutive transient events (reusing
  `df_events` Start/End), trimmed by `steady_exclusion_s` on each side to drop
  the AVR/governor settling tail, then dropped if shorter than
  `steady_dwell_min_s`. No events → whole record is one window.
- `evaluate_steady_window(...)` — checks **every** `Avg_Voltage_LL` /
  `Avg_Frequency` sample (raw `df_proc`, **never `df_interp`**) against the δ
  bands; emits min/mean/max, out-of-band count + %, worst deviation, mean kW →
  `Load_Label` (snapped to 25/50/75/100% when `rated_load_kw` is set), Pass/Fail.
- **Hunting flag** (`_detect_hunting`) — sustained cyclic oscillation
  (governor/AVR hunting) via mean-crossing count + peak-to-peak vs band width.
  A *qualitative red flag only* — it does **not** fail the dwell on its own.
- `analyze_steady_state(df_proc, df_events, config, windows=None)` — orchestrates;
  `windows` lets the caller pass user-confirmed/edited dwells (hybrid flow).

**ISO 8528-5 Table 4 grading (`steady_performance_class`, default None).** Two modes:
- **Legacy / free-form (class None):** unchanged — pass/fail is per-sample against
  the free-form `steady_voltage_band_pct` / `steady_freq_band_pct` δ bands.
- **Class mode (`"G1"/"G2"/"G3"`):** metrics are graded against `STEADY_STATE_LIMITS`
  (the Table 4 dict). `steady_limits(config)` resolves the per-class limits and
  applies the footnote toggles (`steady_single_two_cylinder` → β_f ≤ 2.5%;
  `steady_low_power` → ΔU_st ±10%; `steady_parallel_operation` → unbalance 0.5%;
  `steady_isochronous` → droop 0%). Then:
  - **β_f** (`_beta_f`, spec §2.1) — per-window peak-to-peak `(f_max−f_min)/f_r×100`
    (outlier-robust via `steady_beta_f_percentile`) drives the per-window frequency
    verdict (`Beta_f_pct` / `Beta_f_limit_pct` / `Beta_f_pass`). β_f is always
    reported; it only grades when a class is set. The displayed per-window bands
    switch to the class bands (V = ΔU_st regulation band, F = α_f tol band).
  - **ΔU_st** (cross-window, spec §2.3) — `summarize_steady_state(df_proc, df_windows,
    config)` aggregates the per-window mean voltages into `±(U_max−U_min)/(2·U_r)×100`,
    plus the **droop sanity** check (`(f_noload−f_rated)/f_r×100`) and the §4
    **sample-rate gate** (`detect_sample_rate_hz`). Returns a JSON dict with graded
    `*_pass` fields (None outside class mode).
  - **ΔU_2.0 voltage unbalance** (§2.4) — `summarize_steady_state` computes the IEC
    line-voltage unbalance factor (`_voltage_unbalance_pct`) at the no-load window
    from per-phase magnitudes carried on `df_proc.attrs["v_phase"]`
    (`_extract_per_phase`). **On attrs, NOT columns** — columns would slice into
    `df_events` and leak into the JSON contract + break the parity signature.
    Exact from L-L magnitudes; flagged "approx" from L-N (zero-sequence). Graded
    vs `volt_unbalance_pct`.
  - **§4 sample-rate gate** (`detect_sample_rate_hz` + `_modulation_gate`) sets
    `modulation_status` ("insufficient sample rate" / "AMC (G1)" / "pending") so a
    modulation number is never fabricated from undersampled data (`_MODULATION_MIN_FS_HZ`
    = 50). The **Û_mod,s modulation maths** itself (§2.5) is the only remaining
    deferred metric.

Bridge/contract: `HostBridge.run_analysis` attaches `result["steady"]` (list of
window dicts via `events_to_records`) **and** `result["steady_summary"]` (the
cross-window dict) **only when enabled**, so the default contract is byte-identical.
`HostBridge.recalc_steady({"windows": [...]})` re-evaluates user-edited/labelled
windows against the cached `df_proc` and returns both `steady` + `steady_summary`
(omit `windows` to re-detect). Frontend: sidebar performance-class chips + footnote
toggles + δ-band / dwell inputs; `SteadyStatePanel.svelte` renders the editable
dwell table (with a β_f column) plus the ISO 8528-5 summary card; the report
(`report_host.build_steady_summary_html` + `build_steady_table_html`) embeds both.
`MockBackend` serves the bundled `steady` + `steady_summary` sample.

### Miro logger support (2026-05-05)
Two CSV formats are now auto-detected from the header in `analysis.py:detect_logger_format`:
- **Hioki / generic** — default branch
- **Miro** — fingerprinted by `RMS-VA-AVG [V]`, `FREQ-VA-AVG [Hz]`, `kW-PTOTAL-AVG [kW]` columns

`load_and_prepare_csv` dispatches to `load_miro_csv` for Miro, which:
1. Renames Miro columns to pipeline-standard (`U1/U2/U3_rms_AVG`, `I1/I2/I3_rms_AVG`,
   `Freq_AVG`, `PF_sum_AVG`).
2. Converts `kW-PTOTAL-AVG [kW]` → `P_sum_AVG` in W (× 1000) to match the pipeline's
   `/1000` divisor.
3. **Stable-sorts by Timestamp (`kind="mergesort"`)** so rows sharing a whole-second
   timestamp keep their original CSV row order. Default quicksort scrambled them,
   producing fake `+/-/+` load-step oscillations downstream.
4. **Redistributes same-second rows across the second.** Miro `Timestamp` is
   1 s resolution even when the logger samples at 5–10 Hz, so 5 rows can share
   one timestamp value. Each group of N rows gets `t + (i / N)` second offsets
   so the data carries an honest sub-second grid.
5. Stashes the format on `df.attrs["logger_format"]` for the UI to surface and
   for the Run Analysis path to consult.

Voltages stay in L-N form on read; `ln_to_ll_mode="auto"` detects U1/U2/U3 as
L-N and applies ×√3 downstream. The sidebar shows a coloured pill banner
("Detected logger: Miro" / "Hioki / generic") under the CSV selector — indigo
pill for Miro, green for Hioki — every time a CSV is selected.

**Miro skips the 100ms interpolation.** The compliance Run Analysis path sets
`config.skip_interpolation = True` whenever `df_raw.attrs["logger_format"] == "miro"`,
regardless of the actual sample rate. Rationale: the source rate is whatever the
user configured the logger to record, and inventing 100 ms samples between Miro
readings would obscure the real measurement grid. The recovery algorithm derives
its sustain/verify counts from the actual timestamps so it works correctly at
any rate (see *Recovery requires sustained in-band* above).

### Potential Fault flag (2026-05-05) — separate from compliance fail
Long V or F recovery times on a real generator usually indicate broken set-points
or hardware issues, not just marginal performance. `check_compliance` now emits
two extra fields:
- `Potential_Fault: bool` — True when V_rec_s or F_rec_s exceeds `config.fault_recovery_threshold_s`
- `Fault_Reasons: str` — semi-colon-joined per-fault explanations, e.g.
  `"V Recovery 15.4s > 10s"`

`fault_recovery_threshold_s` (default 10 s) is configurable via a sidebar
input and persisted in `_DEV_DEFAULTS`. The compliance table renderer
(`_render_compliance_html`) shows a new **Potential Fault** column with an
amber `⚠ Investigate` badge (`#fffbeb` / `#b45309`), and the **Failure Reasons**
column appends `⚠ Possible fault: <reasons>` from `Fault_Reasons` so both
contexts surface together. A Pass event can still be flagged Fault if its
recovery is just inside the ISO limit but unusually slow.

### Per-snapshot window + time-shift overrides (2026-05-05)
Each event expander has its own snapshot tuning controls (no longer dev-mode-only):
- **Window size (s)** — per-snapshot override of the global `snapshot_window_s`
- **Time shift (s)** — slide the visible window forwards/backwards along the
  time axis. The event marker stays on its real timestamp; only the visible
  span moves.
- **↺ Apply** — regenerates that one snapshot
- **⟲ Reset** — reverts to the global setting

Persisted in two session-state dicts that are cleared on each Run Analysis:
- `event_window_overrides[event_idx] = float`
- `event_offset_overrides[event_idx] = float`

`plot_load_change_snapshot` accepts a `time_offset_s` parameter that asymmetrically
adjusts `left_s` / `right_s`. When the offset is non-zero the neighbour-event
clamping is skipped — explicit user intent takes priority over the safety guard.
Compliance values are unaffected; only the snapshot image changes.

### Detected Events plot (2026-05-05) — first time-series tab
`visualizations.plot_detected_events(df_proc, df_events, ...)` renders a kW
time-series with every detected event overlaid as an amber vertical dotted line
plus a `+NNN kW` annotation. Saved under graph_paths key `"Detected_Events"`,
which the tab-label code converts to "Detected Events" via the standard
`n.replace("Avg_", "").replace("_", " ")` formatter. Inserted into `graph_paths`
before the regular `Avg_kW` plot so it lands as the first tab in both
Compliance and WinScope sections. The legend includes the event count, which
is the fastest sanity-check for whether detection caught the right number of
load steps.

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

### Deferred snapshot streaming (perceived-perf optimisation)
Run Analysis no longer renders snapshots inline. Snapshots are the dominant
cost (4-panel matplotlib figure at dpi=150 per event), so they're deferred:

1. Run Analysis runs CSV load → `perform_analysis` → time-series plots →
   compliance table, then seeds `snapshot_paths = [None] * len(df_events)`,
   stashes kwargs in `st.session_state["pending_snapshot_args"]`, and sets
   `snapshots_pending = True`. **It does NOT call `generate_all_snapshots`.**
2. The results section renders normally — table, time-series, then snapshot
   expanders. While `snapshots_pending` is True, expanders with `None` paths
   show "Snapshot rendering…" instead of "No snapshot image for this event."
3. A streaming block sits below the snapshot expanders. While
   `snapshots_pending` is True it shows an `st.progress` bar and loops
   `plot_load_change_snapshot` once per event, mutating
   `session_state["snapshot_paths"][i]` after each render. When the loop
   finishes it clears the pending flag and calls `st.rerun()` so the
   expanders refresh with the completed images.
4. Per-snapshot exceptions are collected into
   `session_state["snapshot_stream_errors"]` and surfaced as warnings on the
   next rerun (popped after display).

WinScope mirrors the same pattern with `ws_*` keys
(`ws_snapshots_pending`, `ws_pending_snapshot_args`,
`ws_snapshot_stream_errors`). The WinScope expander loop now iterates over
`_ws_ev` (events) rather than `_ws_sp` (paths) so pending events still get
an expander with the placeholder.

The wall-clock cost is unchanged (still single-threaded matplotlib — keeps
us off the threading-safety landmines), but the table + time-series land
immediately and the user sees snapshots stream in below with live progress.
The legacy `generate_all_snapshots` helper is still used by the
"Recalculate Compliance" path and the report-generation "regenerate clean
snapshots" branch — both are post-analysis flows where deferral isn't
needed.

## Telemetry (added 2026-05-05)

Lightweight usage + error tracking shipped to a Google Sheets webhook so
remote distributed users (Streamlit Cloud free tier) can be observed
without standing up a backend. **Privacy posture: no names, no raw IPs,
no uploaded data ever leaves the app** — only a 12-char salted-IP hash.

### Module: `tracking.py`
- `log_event(event_type, **details)` — writes to `usage` sheet
- `log_error(category, message, **details)` — writes to `errors` sheet
- `log_crash(exc, context)` — writes to `crashes` sheet with traceback
- `log_app_open_once()` — fires `app_open` exactly once per Streamlit session (uses `_telemetry_app_open_logged` session flag)
- `log_preset_change(current)` — fires `preset_changed` only when the active preset differs from the last-seen value (uses `_telemetry_last_preset` session flag)
- `install_global_handlers()` — installs a `sys.excepthook` wrapper that calls `log_crash()` before delegating to the prior hook

All sends run on a daemon thread via `urllib.request`. Failures are
swallowed at every layer — telemetry must never crash or block the UI.
If the `TELEMETRY_WEBHOOK` secret is missing (e.g. local dev), every
call short-circuits to a no-op so dev runs do not pollute the Sheet.

### Wired call sites in `app.py`
| Event | Site | Notes |
|---|---|---|
| `app_open` | After `_build_version` is resolved (just before MAIN AREA layout) | Once-per-session via `log_app_open_once()` |
| `preset_changed` | After `_ds["active_preset"] = active_preset` in the sidebar | Only fires on actual change |
| `analysis_run` (compliance) | After `perform_analysis()` succeeds in the compliance tab | Carries `events`, `nominal_voltage`, `preset` |
| `analysis_run` (winscope) | After `perform_analysis()` succeeds in the WinScope tab | Same payload, `source="winscope"` |
| `report_generated` (compliance) | After report add-to-session succeeds | Carries `format`, `download_format` |
| `report_generated` (winscope) | After WinScope report add-to-session succeeds | Same payload, `source="winscope"` |
| `log_error("csv_format_invalid", ...)` | When `validate_csv_format()` rejects a CSV | Joined error messages capped at 500 chars |
| `log_crash(exc, context=...)` | Compliance analysis failure, both report failures, both setpoint comparison failures, and any uncaught exception via `sys.excepthook` | |

### Required Streamlit secrets
```toml
TELEMETRY_WEBHOOK = "https://script.google.com/macros/s/.../exec"
TELEMETRY_SALT    = "any-random-string-pick-once-and-keep"
```
Changing the salt re-buckets users — pick once, keep forever.

### Google Sheets backend
- One Sheet (`PQA Telemetry`) with three tabs: `usage`, `errors`, `crashes`.
- Header rows must match payload keys — Apps Script reads the header row and maps payload fields by name, so column order in the Sheet is flexible but **header names are load-bearing**.
  - `usage`: `timestamp | user_hash | app_version | event_type | details`
  - `errors`: `timestamp | user_hash | app_version | category | message | details`
  - `crashes`: `timestamp | user_hash | app_version | error_type | message | context | traceback`
- Apps Script `doPost(e)` parses JSON, looks up sheet by `data.sheet`, appends a row in header order. Deployed as Web app with **Anyone** access (token is the obscure URL).

### Why this design (vs alternatives considered)
- Local JSONL was rejected: Streamlit Cloud free tier filesystem is **ephemeral** (wiped on restart/redeploy/sleep), so logs would not persist.
- Email-per-event was rejected: too noisy for ~10 users × multiple events/day.
- GitHub PAT commits were rejected: PAT shipped in app code is a leak risk.
- Google Sheets via Apps Script: zero infra, free, owner-controlled, no auth in shipped code (just the webhook URL in `st.secrets`).

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
  Same applies to `event_window_overrides` and `event_offset_overrides`
  (per-snapshot size + time-shift) — both are wiped on Run Analysis.
- **Miro CSV stable sort is load-bearing.** `load_miro_csv` uses
  `sort_values("Timestamp", kind="mergesort")` because pandas' default
  quicksort is unstable; with multiple rows sharing the same whole-second
  timestamp it scrambled their order, and the subsequent sub-second
  redistribution produced fake `+/-/+` load-step oscillations. Do not
  switch this to the default sort.
- **Logging noise:** `matplotlib`, `PIL`, `fontTools`, `asyncio`, and
  `urllib3` are silenced at WARNING in the global logging setup
  (`app.py` ~line 50). Without this they emit hundreds of lines per
  generated plot at DEBUG level and drown `pqa_debug.log`.
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
- **CSV encoding fallback:** logger CSVs frequently contain cp1252/latin-1
  bytes (e.g. `°` = `0xB0`) and `pd.read_csv` defaults to UTF-8. Both real
  read sites are now defended:
  - `analysis.py:load_and_prepare_csv` — `try` UTF-8, `except UnicodeDecodeError` retry with `encoding="latin-1"` (header peek and main read both wrapped).
  - `app.py` preview pane (~line 2675) — uses `encoding="utf-8", encoding_errors="replace"` so non-UTF-8 bytes render as `�` in the 10-row preview instead of raising.
  Any new `pd.read_csv` call against user-supplied CSVs needs the same defence.
