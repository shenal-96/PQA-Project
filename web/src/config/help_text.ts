// Per-field help text for the configuration sidebar — the desktop equivalent of
// the Streamlit app's `help=` tooltips, rendered by InfoTip.svelte as a "?" icon
// next to each field/toggle. Strings for fields that exist in the Streamlit
// sidebar are ported verbatim from app.py; the steady-state entries are written
// fresh (steady-state had no Streamlit UI) from the PQA user guide.

export const HELP = {
  // ── File ──────────────────────────────────────────────────────────
  file:
    'Load the data-logger file to analyse. PQA auto-detects the format (Hioki / generic or Miro for CSV; WinScope for .xls) and shows it as a pill below the file name.',

  // ── Time Window ───────────────────────────────────────────────────
  time_start:
    'Restrict analysis to start at this time. Leave blank to start at the beginning of the file.',
  time_end:
    'Restrict analysis to end at this time. Leave blank to run to the end of the file.',

  // ── Acceptance Criteria ───────────────────────────────────────────
  active_preset:
    'Apply a saved set of acceptance criteria (ISO 8528 G1 / G2 / G3 or your own). Selecting a preset fills in all the limits below; choose None to set them manually.',
  manage_presets: 'Edit the built-in presets or create and save your own.',

  show_limits:
    'Overlay max deviation limit lines (red dashed) on the full time-series voltage and frequency plots.',

  snapshot_display:
    'Choose which reference markers are drawn on the per-event snapshot plots.',
  show_tolerance_band:
    'Draw the recovery tolerance band (amber dashed lines) on each event snapshot plot.',
  show_deviation_limits:
    'Draw the max deviation limit lines (red dashed) on each event snapshot plot.',
  show_intersections:
    'Overlay the exact band-exit (orange ★) and recovery (lime ★) crossing markers on event snapshots, along with the compliance band limits used for each event. Useful for verifying that calculated recovery times match the waveform.',
  show_max_deviation:
    'Mark the actual peak voltage and frequency deviation point on each event snapshot (red ★) with a legend entry showing the measured value.',

  detection_window_s:
    'Time window used to group consecutive load-step rows into a single event. Changes within this window are merged into one net step by algebraic sum.',
  snapshot_window_s:
    'Total seconds shown around each event (centred: ±window/2). Also sets the window used to find the peak voltage / frequency deviation.',
  recovery_verify_s:
    'After a recovery candidate is found, verify the signal stays in-band for this many seconds. Handles oscillating waveforms.',
  fault_recovery_threshold_s:
    'Recovery times longer than this are flagged as a Potential Fault — separate from compliance fail. Indicates broken set-points or hardware issues.',
  load_threshold_kw:
    'Minimum load step size (kW) to register as a compliance event. Changes smaller than this are ignored.',

  apply_asymmetric_volt:
    'Enable separate recovery band limits for voltage — one set for load increase events (voltage drops) and another for load decrease (voltage rises). Unlocks the Voltage Recovery Bands inputs below.',
  apply_asymmetric_volt_dev:
    'Enable separate max deviation limits for voltage — one for load increase events (voltage drops below nominal) and another for load decrease (voltage rises above nominal). Unlocks the Voltage Max Deviation inputs below.',
  apply_asymmetric_freq:
    'Enable separate recovery band limits for frequency — one set for load increase events (frequency drops) and another for load decrease (frequency rises). Unlocks the Frequency Recovery Bands inputs below.',
  apply_asymmetric_freq_dev:
    'Enable separate max deviation limits for frequency — one for load increase events (frequency drops below nominal) and another for load decrease (frequency rises above nominal). Unlocks the Frequency Max Deviation inputs below.',
  iso_8528_5_mode:
    'Optional ISO 8528-5 §7 method for frequency only. The recovery stopwatch STARTS when frequency leaves the tighter β_f start band and STOPS when it re-enters the wider α_f stop band (vs a single band for both). Also adds pre-step and post-recovery steady-state checks. Off = single-band behaviour. The ISO G1/G2/G3 presets enable this. Unlocks the ISO 8528-5 Frequency Bands inputs below.',

  voltage_tolerance_pct:
    'Symmetric ±% band around nominal voltage used as the recovery target. Voltage must re-enter this band and stay in for 0.3 s to be considered recovered.',
  voltage_recovery_time_s:
    'Maximum allowed recovery time for voltage after a load event. Events where voltage takes longer than this to return in-band fail compliance.',
  voltage_max_deviation_pct:
    'Maximum allowed voltage excursion from nominal (%). Events where the peak deviation exceeds this value fail compliance regardless of recovery time.',
  frequency_tolerance_pct:
    'Symmetric ±% band around nominal frequency used as the recovery target. Frequency must re-enter this band and stay in for 0.3 s to be considered recovered.',
  frequency_recovery_time_s:
    'Maximum allowed recovery time for frequency after a load event. Events where frequency takes longer than this to return in-band fail compliance.',
  frequency_max_deviation_pct:
    'Maximum allowed frequency excursion from nominal (%). Events where the peak deviation exceeds this value fail compliance regardless of recovery time.',

  // ── Asymmetric voltage recovery bands (V) ─────────────────────────
  volt_recovery_upper_increase:
    'Upper recovery band limit (V) for load increase events (voltage drops). Voltage must re-enter below this level to start the recovery timer.',
  volt_recovery_lower_increase:
    'Lower recovery band limit (V) for load increase events (voltage drops). Voltage must re-enter above this level to start the recovery timer.',
  volt_recovery_upper_decrease:
    'Upper recovery band limit (V) for load decrease events (voltage rises). Voltage must re-enter below this level to start the recovery timer.',
  volt_recovery_lower_decrease:
    'Lower recovery band limit (V) for load decrease events (voltage rises). Voltage must re-enter above this level to start the recovery timer.',

  // ── Asymmetric voltage max deviation (%) ──────────────────────────
  volt_max_dev_pct_increase:
    'Max allowed voltage drop as a % of nominal for load increase events. Voltage below nom × (1 − this%) fails compliance.',
  volt_max_dev_pct_decrease:
    'Max allowed voltage rise as a % of nominal for load decrease events. Voltage above nom × (1 + this%) fails compliance.',

  // ── Asymmetric frequency recovery bands (Hz) ──────────────────────
  freq_recovery_upper_increase:
    'Upper recovery band (Hz) for load increase events (frequency drops). ISO 8528 default: 50.50 Hz.',
  freq_recovery_lower_increase:
    'Lower recovery band (Hz) for load increase events (frequency drops). ISO 8528 default: 49.75 Hz.',
  freq_recovery_upper_decrease:
    'Upper recovery band (Hz) for load decrease events (frequency rises). ISO 8528 default: 50.25 Hz.',
  freq_recovery_lower_decrease:
    'Lower recovery band (Hz) for load decrease events (frequency rises). ISO 8528 default: 49.50 Hz.',

  // ── Asymmetric frequency max deviation (%) ────────────────────────
  freq_max_dev_pct_increase:
    'Max allowed frequency drop as a % of nominal for load increase events. Frequency below nom × (1 − this%) fails compliance.',
  freq_max_dev_pct_decrease:
    'Max allowed frequency rise as a % of nominal for load decrease events. Frequency above nom × (1 + this%) fails compliance.',

  // ── ISO 8528-5 dual frequency bands ───────────────────────────────
  band_mode:
    'pct: enter β_f (start) and α_f (stop) total band widths as % of nominal — auto-scaled to the active nominal frequency. abs: enter the absolute Hz band limits directly.',
  beta_f_pct:
    'Steady-state frequency band β_f as a total (peak-to-peak) % of nominal. The stopwatch STARTS when frequency leaves this tighter band. ISO 8528-5: G3 = 0.5, G2 = 1.5, G1 = 2.5.',
  alpha_f_pct:
    'Tolerance frequency band α_f as a total (peak-to-peak) % of nominal. The stopwatch STOPS when frequency permanently re-enters this wider band. ISO 8528-5: G3 = 2.0, G2 = 2.0, G1 = 3.5.',
  freq_start_upper:
    'Upper β_f start-band limit (Hz). Frequency rising above this starts the recovery stopwatch.',
  freq_start_lower:
    'Lower β_f start-band limit (Hz). Frequency dropping below this starts the recovery stopwatch.',
  f_stop_upper:
    'Upper α_f stop-band limit (Hz). Frequency must re-enter below this (and stay) to stop the recovery stopwatch.',
  f_stop_lower:
    'Lower α_f stop-band limit (Hz). Frequency must re-enter above this (and stay) to stop the recovery stopwatch.',

  // ── Steady-state (ISO 8528-5 δ bands) ─────────────────────────────
  steady_state_enabled:
    'Evaluate generator stability during the stable dwell periods between load steps (ISO 8528-5 δ bands). Opt-in — only meaningful for staged load-bank tests that hold 25 / 50 / 75 / 100 % for a dwell. Separate from the transient recovery checks above.',
  steady_performance_class:
    'ISO 8528-5 Table 4 grade. None = free-form: every sample is checked against your δU / δf bands. G1 / G2 / G3 = grade frequency on β_f (peak-to-peak) and voltage on ΔU_st (regulation) against that class’s Table 4 limits.',
  steady_isochronous:
    'Isochronous set — the engine holds constant speed with no droop. Sets the droop limit to 0 % when grading. On by default.',
  steady_single_two_cylinder:
    'Single- or two-cylinder engine — ISO 8528-5 footnote relaxes the β_f frequency band to ≤ 2.5 % for any class.',
  steady_low_power:
    'Low-power set graded under ISO 8528-8 — relaxes the ΔU_st voltage regulation limit to ±10 %.',
  steady_parallel_operation:
    'Set running in parallel — tightens the no-load voltage unbalance limit to 0.5 %.',
  steady_voltage_band_pct:
    'δU — voltage tolerance during a dwell (± % of nominal). In free-form (class None) mode a window fails if any sample leaves this band. In class mode it drives the time-series overlay only.',
  steady_freq_band_pct:
    'δf — frequency tolerance during a dwell (± % of nominal). In free-form (class None) mode a window fails if any sample leaves this band. In class mode it drives the time-series overlay only.',
  steady_dwell_min_s:
    'Ignore dwell windows shorter than this. Set it below your actual hold time so real plateaus survive but brief pauses between steps don’t.',
  steady_exclusion_s:
    'Trim this many seconds off each side of a dwell to drop the post-step governor / AVR settling tail. Raise it if a slow governor drags transient samples into the dwell.',

  // ── Reporting helpers ─────────────────────────────────────────────
  rated_load_kw:
    'When set, the load change is shown as a % of rated on snapshots, and each steady-state dwell is auto-labelled 25 / 50 / 75 / 100 %. Optional.',
  expected_steps:
    'Optional. If set, a warning is shown when the number of detected events doesn’t match this count.',

  // ── Display Options ───────────────────────────────────────────────
  nominal_voltage:
    'Reference L-L voltage for compliance checks and deviation calculations. Pick a preset or choose Custom to enter a value directly. All voltage deviation percentages and recovery bands are relative to this.',
  nominal_frequency:
    'Reference frequency (Hz) for compliance checks. All frequency deviation percentages and recovery bands are relative to this value.',
  ln_to_ll_mode:
    'How to read the CSV voltage columns. Auto-detect uses column names: U12/U23/U31 = L-L (used as-is), U1/U2/U3 = L-N (×√3 to L-L). Override if your logger uses non-standard names. Compliance is always checked against L-L.',
} as const;

export type HelpKey = keyof typeof HELP;
