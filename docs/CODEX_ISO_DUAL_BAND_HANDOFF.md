# Codex Handoff — Fix ISO 8528-5 Dual Frequency Bands (desktop app)

**Branch:** `claude/gifted-pasteur-kf2l2i` (PR #31). Reference branch: `origin/streamlit-legacy`.
**Symptom (from the owner):** In the desktop app the ISO 8528-5 "dual frequency
bands" feature is not working — **both bands are not plotted correctly**, and the
**analysis/evaluation is wrong**. The owner is confident it worked in the
Streamlit app. Your job: inspect the Streamlit implementation, find every place
the desktop port diverges, and fix it so the desktop behaves identically.

---

## 0. The single most important fact (verified — don't re-litigate)

The **analysis engine is the SAME on both branches.** I diffed
`origin/streamlit-legacy:core/analysis.py` against `HEAD:core/analysis.py`: the
only differences are line-number offsets plus unrelated additions on `main`
(`filter_time_window`, time-window plumbing). **Every ISO 8528-5 code path in the
engine is identical** (`check_compliance` §7 steady-state block; the
`F_start_upper`/`F_start_lower` per-event columns; the `freq_start_*` config
fields; `_steady_after_recovery`).

Verify yourself before changing anything:
```bash
diff <(git show origin/streamlit-legacy:core/analysis.py) <(git show HEAD:core/analysis.py)
```
**Conclusion: do NOT change `core/analysis.py`'s ISO logic.** The engine reads
these `AnalysisConfig` fields and trusts them:
- `iso_8528_5_mode: bool`
- `freq_start_upper_increase / freq_start_lower_increase / freq_start_upper_decrease / freq_start_lower_decrease`  → the **β_f START band** (stopwatch starts when freq leaves this)
- `freq_recovery_upper_increase / lower_increase / upper_decrease / lower_decrease` → in ISO mode these ARE the **α_f STOP band** (stopwatch stops on re-entry / recovery target)
- `frequency_tolerance_pct` → the ΔU_st **steady-state** band (nom ± tol) used by the §7 pre/post steady-state checks.

So the bug is entirely in **(a) how the desktop frontend RESOLVES and SENDS these
config values**, and **(b) how the desktop renders the two bands**. Focus there.

---

## 1. Read the Streamlit reference first (this is the spec)

Read these exact locations on `origin/streamlit-legacy` and write down the algorithm:

### 1a. Preset definitions + the band resolver — `app.py`
```bash
git show origin/streamlit-legacy:app.py | sed -n '118,260p'
```
Key things you will find:
- **Preset seeds (lines ~120–145):** each ISO preset sets
  `"iso_8528_5": True, "band_mode": "pct", "beta_f_pct": …, "alpha_f_pct": …,
  "f_start_upper": …, "f_start_lower": …, "f_stop_upper": …, "f_stop_lower": …`.
  Example G3: `beta_f_pct 0.5, alpha_f_pct 2.0, f_start 50.125/49.875, f_stop 50.50/49.50`.
  G2: `beta_f 1.5, alpha_f 2.0, f_start 50.375/49.625, f_stop 50.50/49.50`.
  G1: `beta_f 2.5, alpha_f 3.5, f_start 50.625/49.375, f_stop 50.875/49.125`.
  **These are at 50 Hz nominal.** `band_mode="pct"` means they are recomputed for
  the active nominal frequency from `beta_f_pct`/`alpha_f_pct` (see resolver).
- **`_resolve_iso_freq_bands(...)` (lines ~166–208):** THE canonical mapping. Read
  the whole body. It returns, in order:
  `(rec_up_inc, rec_lo_inc, rec_up_dec, rec_lo_dec,  # α_f STOP band == the freq RECOVERY band the engine uses
    start_up_inc, start_lo_inc, start_up_dec, start_lo_dec)  # β_f START band`
  - When `band_mode == "pct"`: `bf_half = (beta_f_pct/2)/100*nom_f`,
    `af_half = (alpha_f_pct/2)/100*nom_f`; start band = `nom_f ± bf_half`,
    stop band = `nom_f ± af_half` (confirm exact symmetry/asymmetry in the source).
  - When `band_mode == "abs"`: use `f_start_*` / `f_stop_*` directly.
  - **Critical:** the α_f STOP band becomes the engine's `freq_recovery_*` band.
    The β_f START band becomes the engine's `freq_start_*`. This is the coupling
    the desktop is missing.

### 1b. Snapshot drawing (both bands) — `visualizations.py`
```bash
git show origin/streamlit-legacy:visualizations.py | sed -n '815,1030p'
```
Key behaviour (frequency panel):
- The **α_f recovery/stop band** is drawn (the normal tolerance band lines).
- The **β_f start band** is drawn separately (lines ~977–980): cyan dotted,
  labelled `β_f start upper/lower (xx.xxx Hz)`, only when
  `event_row["F_start_upper"]`/`F_start_lower` are non-null.
- The **exit marker sits on the β_f start band** (lines ~984–986):
  `f_exit_band_val = f_start_upper if f_dev>nom_f else f_start_lower`.
- Legend entries for both bands (lines ~1021–1022).
- Also check whether `generate_plots` (the main frequency **time-series**, not the
  snapshot) draws the bands under `show_limits` — search `visualizations.py` for
  the frequency band drawing in `generate_plots` and replicate if the owner
  expects bands on the time-series too.

### 1c. Engine usage (read-only — confirm, don't change)
```bash
git show origin/streamlit-legacy:core/analysis.py | sed -n '690,720p;950,1010p;1070,1160p'
```
Confirm the engine uses `freq_start_*` for the exit/stopwatch-start and
`freq_recovery_*` (== α_f stop) for recovery, and `frequency_tolerance_pct` for
the §7 steady-state band. (Same on `main`.)

---

## 2. The desktop port — where it is, and the likely bugs

### Files in play (on this branch / `HEAD`)
- `web/src/config/defaults.ts` — `AnalysisConfigInput`, `DEFAULT_CONFIG`,
  `BUILTIN_PRESETS`, **`resolveConfig()`** (builds the dict sent to
  `runAnalysis`). **Primary suspect.**
- `web/src/lib/Sidebar.svelte` — the "Apply ISO dual frequency bands" checkbox
  (`config.iso_8528_5_mode`) and the β_f start-band inputs (`freq_start_*`), plus
  the "Frequency Recovery Bands" inputs (`freq_recovery_*`).
- `core/viz_dataprep.py` — `snapshot_data` / `_decorate`: emits `panel["band"]`
  (α_f recovery) and `panel["start_band"]` (β_f) for the frequency panel, and the
  `exit` marker value. (Lines ~133–148.)
- `web/src/lib/SnapshotChart.svelte` — draws `p.band` (amber dashed) and
  `p.start_band` (cyan dotted) via `markLine` (lines ~30–37).
- `web/src/lib/TimeSeriesChart.svelte` — main frequency time-series (no bands today).

### Confirmed/likely bugs (verify each, then fix)

**BUG 1 — Presets don't enable or set the dual bands (highest priority).**
`BUILTIN_PRESETS` in `defaults.ts` do **not** set `iso_8528_5_mode: true`, nor the
β_f `freq_start_*`, nor the correct α_f stop band. In Streamlit, selecting an ISO
preset ENABLES the two-band method and sets both bands. On desktop, selecting
"ISO 8528 G3" leaves `iso_8528_5_mode` false and the start band at defaults, so
the engine never runs dual-band logic and the snapshot never gets `start_band`.
→ Port the Streamlit preset ISO values (§1a) into each `BUILTIN_PRESETS` entry:
set `iso_8528_5_mode: true` and the four `freq_start_*` (β_f) and four
`freq_recovery_*` (α_f stop) values. Use the 50 Hz numbers from §1a, OR — better —
compute them from `beta_f_pct`/`alpha_f_pct` for `nominal_frequency` to match the
Streamlit `band_mode="pct"` behaviour (see BUG 2).

**BUG 2 — `resolveConfig()` sends the WRONG frequency recovery band in ISO mode.**
Today `resolveConfig` sets `freq_recovery_*` from the asymmetric toggle/tolerance
ONLY:
```
freq_recovery_upper_increase: c.apply_asymmetric_freq ? c.freq_recovery_upper_increase : fUp,  // fUp = nom*(1+tol/100)
```
This is independent of `iso_8528_5_mode`. So if the user enables ISO but not
`apply_asymmetric_freq`, the engine's recovery/stop band collapses to the
symmetric ±tol steady-state band — **wrong α_f band → wrong recovery times →
wrong pass/fail.** In Streamlit the α_f STOP band is the recovery band whenever
ISO mode is on.
→ Fix: when `c.iso_8528_5_mode` is true, the emitted `freq_recovery_*` must be the
**α_f stop band** (from the preset / β_f-α_f % resolver, mirroring
`_resolve_iso_freq_bands`), regardless of `apply_asymmetric_freq`. Replicate
`_resolve_iso_freq_bands` in TS as a helper and call it from `resolveConfig` when
`iso_8528_5_mode` is on; otherwise keep the existing non-ISO logic. The β_f
`freq_start_*` are already passed through (confirm they are).

**BUG 3 — Snapshot shows only one band (follow-on from 1 & 2).**
`_decorate` only adds `panel["start_band"]` when the event row carries
`F_start_upper`/`F_start_lower`, which the engine only emits when
`iso_8528_5_mode` is true. Once BUGs 1–2 make ISO mode actually engage, the
cyan β_f band should appear. **Verify both bands now render:** α_f recovery
(amber dashed) AND β_f start (cyan dotted), and that the **exit marker sits on the
β_f band** (`core/viz_dataprep._decorate` already sets
`exit_val = start_upper/start_lower if has_start` — confirm it matches Streamlit
§1b, lines ~984–986). Confirm `SnapshotChart.svelte` is gated on the right `SHOW`
flag (it currently keys the start band off `SHOW.band` — make sure that's the
intended toggle; Streamlit always draws β_f when present).

**BUG 4 — (verify) bands on the main frequency time-series.**
Check whether the owner expects the α_f and β_f bands drawn on the **frequency
time-series tab** (not just snapshots). If Streamlit's `generate_plots` draws them
under `show_limits`, add horizontal lines to `TimeSeriesChart.svelte` for the
frequency metric (pass band values through). If only snapshots show bands in
Streamlit, skip this.

**BUG 5 — (verify) Sidebar exposes the α_f stop band correctly.**
Today the Sidebar shows β_f start inputs (when ISO on) and a separate
"Frequency Recovery Bands" group (gated on `apply_asymmetric_freq`). Make the
relationship explicit: in ISO mode the "Frequency Recovery Bands" ARE the α_f
stop band and should be shown/edited as such (independent of
`apply_asymmetric_freq`). Consider adding `beta_f_pct` / `alpha_f_pct` numeric
inputs (matching Streamlit) so the bands can be driven by percentage and
recomputed on nominal-frequency change. Keep the labels: "β_f start band",
"α_f stop band (= frequency recovery band)".

---

## 3. Concrete implementation plan

1. **Port the band resolver to TS.** In `defaults.ts` add
   `resolveIsoFreqBands(nom_f, band_mode, beta_f_pct, alpha_f_pct, f_start_*,
   f_stop_*)` that returns `{ rec_up_inc, rec_lo_inc, rec_up_dec, rec_lo_dec,
   start_up_inc, start_lo_inc, start_up_dec, start_lo_dec }`, a faithful port of
   Streamlit `_resolve_iso_freq_bands` (app.py ~166–208). Add the supporting
   config fields if you adopt the pct path: `band_mode`, `beta_f_pct`,
   `alpha_f_pct`, `f_start_upper/lower`, `f_stop_upper/lower` (mirror Streamlit
   preset keys), to `AnalysisConfigInput` + `DEFAULT_CONFIG`.
2. **Fix `BUILTIN_PRESETS`** (BUG 1): each ISO preset sets `iso_8528_5_mode:true`
   and the β_f + α_f values (or the pct inputs that resolve to them).
3. **Fix `resolveConfig`** (BUG 2): when `iso_8528_5_mode`, override
   `freq_recovery_*` (α_f stop) and `freq_start_*` (β_f) from the resolver; keep
   `iso_8528_5_mode` passthrough. Leave non-ISO path unchanged.
4. **Verify/适配 snapshot rendering** (BUG 3): confirm `core/viz_dataprep._decorate`
   emits `start_band` + exit-on-β_f, and `SnapshotChart.svelte` draws both bands
   with correct colors (α_f amber dashed, β_f cyan dotted) and legend. Adjust the
   `SHOW` gating if β_f disappears when it shouldn't.
5. **(If needed) main time-series bands** (BUG 4) and **Sidebar clarity** (BUG 5).
6. **Regenerate the browser dev sample** so the demo exercises ISO mode:
   - Temporarily, or via a dedicated sample, run the bridge with an ISO config so
     `events` carry `F_start_upper/lower`. Then
     `python web/scripts/gen_sample.py` (note: it currently runs `run_analysis({})`
     with no ISO config — consider adding an ISO-config variant sample, or verify
     manually in the desktop app instead).

---

## 4. Verification checklist (must pass)

- `python -m pytest tests/ -q` stays green (engine untouched). **Add** an
  engine-level test that runs `perform_analysis` with `iso_8528_5_mode=True` and a
  β_f start band tighter than the α_f stop band, asserting: (a) events carry
  `F_start_upper/lower`; (b) `F_exit_ts` is driven by leaving the β_f band; (c)
  `F_rec_s` measured to α_f re-entry differs from the non-ISO run; (d) §7
  steady-state reasons populate when appropriate. Mirror an existing
  `tests/test_*` style; reuse `tests/fixtures/hioki_sample.csv`.
- Add a `core/viz_dataprep` test asserting the frequency panel emits BOTH
  `band` (α_f) and `start_band` (β_f) and that `exit.value` equals the β_f bound
  for the event direction.
- `cd web && npm run check` → 0 errors; `npm run build` succeeds.
- Manual (desktop, or browser demo if you wire an ISO sample): select an ISO
  preset → frequency snapshots show **two** bands (amber α_f + cyan β_f), exit
  marker on β_f, recovery marker on α_f; recovery times and pass/fail change vs
  non-ISO.

## 5. Guardrails
- Do **not** modify `core/analysis.py` ISO logic — it's already correct and shared
  with the live Streamlit app. Only add tests around it.
- Keep `core/` pure (no host/UI imports) — the future Pyodide path depends on it.
- The α_f "stop" band and the engine field name `freq_recovery_*` are the SAME
  thing — don't introduce a parallel field; map onto the existing engine fields.
- Commit on `claude/gifted-pasteur-kf2l2i`; keep PR #31 a draft; trailers per
  ROADMAP. Update ROADMAP's ISO note when done.
```bash
# orient yourself
git show origin/streamlit-legacy:app.py | sed -n '118,260p'
git show origin/streamlit-legacy:visualizations.py | sed -n '815,1030p'
sed -n '1,266p' web/src/config/defaults.ts          # resolveConfig + presets
sed -n '110,230p' core/viz_dataprep.py              # _decorate freq bands
sed -n '1,130p' web/src/lib/SnapshotChart.svelte    # band drawing
```
