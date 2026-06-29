// Analysis + display configuration, mirroring the Streamlit app's sidebar exactly
// (Acceptance Criteria + Display Options). The raw inputs here are resolved into
// the engine's AnalysisConfig shape by resolveConfig() before runAnalysis(), which
// applies the same asymmetric-toggle logic as app.py (off → symmetric band from
// the tolerance %, on → the explicit per-direction bands).

export type LnToLlMode = 'auto' | 'force_ll' | 'force_ln';

export interface AnalysisConfigInput {
  // ── Display Options (nominal + voltage interpretation) ──
  nominal_voltage: number;
  nominal_frequency: number;
  ln_to_ll_mode: LnToLlMode;

  // ── Detection / snapshot / recovery windows ──
  load_threshold_kw: number;
  detection_window_s: number;
  snapshot_window_s: number;
  recovery_verify_s: number;
  fault_recovery_threshold_s: number;

  // ── Symmetric tolerances / recovery / max-deviation ──
  voltage_tolerance_pct: number;
  voltage_recovery_time_s: number;
  voltage_max_deviation_pct: number;
  frequency_tolerance_pct: number;
  frequency_recovery_time_s: number;
  frequency_max_deviation_pct: number;

  // ── Asymmetric toggles (gate the per-direction inputs below) ──
  apply_asymmetric_volt: boolean;       // voltage recovery bands
  apply_asymmetric_volt_dev: boolean;   // voltage max-deviation
  apply_asymmetric_freq: boolean;       // frequency recovery bands
  apply_asymmetric_freq_dev: boolean;   // frequency max-deviation

  // ── ISO 8528-5 dual frequency bands (β_f start / α_f stop) ──
  // When on, the frequency stopwatch STARTS when freq leaves the tighter β_f
  // start band and STOPS when it re-enters the α_f stop band (= freq recovery
  // bands, overridden from the pct/abs resolver below). Also enables §7 checks.
  iso_8528_5_mode: boolean;
  // Band resolver mode: 'pct' scales with nominal frequency; 'abs' uses Hz directly.
  band_mode: 'pct' | 'abs';
  beta_f_pct: number;   // β_f full-band width as % of nominal (e.g. 0.5 → ±0.25%)
  alpha_f_pct: number;  // α_f full-band width as % of nominal (e.g. 2.0 → ±1%)
  // β_f start band in absolute Hz (used in abs mode; pct mode recomputes these).
  freq_start_upper_increase: number;
  freq_start_lower_increase: number;
  freq_start_upper_decrease: number;
  freq_start_lower_decrease: number;
  // α_f stop band in absolute Hz (used in abs mode; pct mode recomputes these).
  f_stop_upper: number;
  f_stop_lower: number;

  // ── Asymmetric voltage recovery bands (absolute V) ──
  volt_recovery_upper_increase: number;
  volt_recovery_lower_increase: number;
  volt_recovery_upper_decrease: number;
  volt_recovery_lower_decrease: number;
  // ── Asymmetric frequency recovery bands (absolute Hz) ──
  freq_recovery_upper_increase: number;
  freq_recovery_lower_increase: number;
  freq_recovery_upper_decrease: number;
  freq_recovery_lower_decrease: number;
  // ── Asymmetric max-deviation (%) ──
  volt_max_dev_pct_increase: number;
  volt_max_dev_pct_decrease: number;
  freq_max_dev_pct_increase: number;
  freq_max_dev_pct_decrease: number;

  // ── Display flags (not analysis — drive snapshots/report rendering) ──
  show_limits: boolean;
  // Master toggle nesting the four snapshot-marker flags below. When false, none
  // of the per-event snapshot markers are drawn regardless of their own values.
  show_data_points: boolean;
  show_tolerance_band: boolean;
  show_deviation_limits: boolean;
  show_intersections: boolean;
  show_max_deviation: boolean;

  // ── ISO 8528-5 steady-state (δ band) evaluation ──
  // Opt-in, for staged load-bank tests only. Evaluates every sample during the
  // stable dwell periods against the tight δU / δf bands (NOT the α/β recovery
  // bands). See core/analysis.analyze_steady_state.
  steady_state_enabled: boolean;
  steady_voltage_band_pct: number;     // δU around nominal V (±%)
  steady_freq_band_pct: number;        // δf around nominal frequency (±%)
  steady_dwell_min_s: number;          // ignore plateaus shorter than this
  steady_exclusion_s: number;          // trim each side of a dwell (settling tail)
  // ISO 8528-5 performance class for Table 4 grading (null = legacy free-form δ
  // bands). When set, β_f drives the per-window frequency verdict and ΔU_st the
  // cross-window voltage verdict. The flags below are Table 4 footnote toggles.
  steady_performance_class: 'G1' | 'G2' | 'G3' | null;
  steady_single_two_cylinder: boolean; // footnote a — β_f up to 2.5% any class
  steady_low_power: boolean;           // footnotes f/g — ΔU_st ±10% (ISO 8528-8)
  steady_parallel_operation: boolean;  // footnote h — unbalance 0.5% in parallel
  steady_isochronous: boolean;         // footnote q — droop → 0%

  // ── Reporting helpers ──
  rated_load_kw: number | null;        // % rated annotations + steady dwell labels when set
  expected_steps: number | null;       // warn if detected event count differs
}

export const DEFAULT_CONFIG: AnalysisConfigInput = {
  nominal_voltage: 415,
  nominal_frequency: 50,
  ln_to_ll_mode: 'auto',

  load_threshold_kw: 50,
  detection_window_s: 5,
  snapshot_window_s: 10,
  recovery_verify_s: 6,
  fault_recovery_threshold_s: 10,

  voltage_tolerance_pct: 1.0,
  voltage_recovery_time_s: 4.0,
  voltage_max_deviation_pct: 15.0,
  frequency_tolerance_pct: 0.5,
  frequency_recovery_time_s: 3.0,
  frequency_max_deviation_pct: 7.0,

  apply_asymmetric_volt: false,
  apply_asymmetric_volt_dev: false,
  apply_asymmetric_freq: false,
  apply_asymmetric_freq_dev: false,

  iso_8528_5_mode: false,
  band_mode: 'pct',
  beta_f_pct: 0.5,
  alpha_f_pct: 2.0,
  freq_start_upper_increase: 50.125,
  freq_start_lower_increase: 49.875,
  freq_start_upper_decrease: 50.125,
  freq_start_lower_decrease: 49.875,
  f_stop_upper: 50.5,
  f_stop_lower: 49.5,

  volt_recovery_upper_increase: 419.15,
  volt_recovery_lower_increase: 410.85,
  volt_recovery_upper_decrease: 419.15,
  volt_recovery_lower_decrease: 410.85,
  freq_recovery_upper_increase: 50.5,
  freq_recovery_lower_increase: 49.75,
  freq_recovery_upper_decrease: 50.25,
  freq_recovery_lower_decrease: 49.5,
  volt_max_dev_pct_increase: 15,
  volt_max_dev_pct_decrease: 15,
  freq_max_dev_pct_increase: 7,
  freq_max_dev_pct_decrease: 7,

  show_limits: false,
  show_data_points: true,
  show_tolerance_band: true,
  show_deviation_limits: true,
  show_intersections: true,
  show_max_deviation: true,

  steady_state_enabled: false,
  steady_voltage_band_pct: 2.5,
  steady_freq_band_pct: 2.0,
  steady_dwell_min_s: 30,
  steady_exclusion_s: 10,
  steady_performance_class: null,
  steady_single_two_cylinder: false,
  steady_low_power: false,
  steady_parallel_operation: false,
  steady_isochronous: true,

  rated_load_kw: null,
  expected_steps: null,
};

export const VOLTAGE_PRESETS = [415, 690, 11000];

export interface Preset {
  name: string;
  values: Partial<AnalysisConfigInput>;
}

// Built-in ISO 8528 presets (seed values + asymmetric flags from CLAUDE.md).
// All set apply_asymmetric_freq / volt_dev / freq_dev = true, volt band = false.
export const BUILTIN_PRESETS: Preset[] = [
  {
    name: 'ISO 8528 G3',
    values: {
      voltage_tolerance_pct: 1.0, voltage_recovery_time_s: 4.0,
      voltage_max_deviation_pct: 15, volt_max_dev_pct_increase: 15, volt_max_dev_pct_decrease: 20,
      frequency_tolerance_pct: 0.5, frequency_recovery_time_s: 3.0,
      frequency_max_deviation_pct: 7, freq_max_dev_pct_increase: 7, freq_max_dev_pct_decrease: 10,
      // Asymmetric α_f stop band used when NOT in ISO dual-band mode (fallback).
      freq_recovery_upper_increase: 50.5, freq_recovery_lower_increase: 49.75,
      freq_recovery_upper_decrease: 50.25, freq_recovery_lower_decrease: 49.5,
      apply_asymmetric_freq: true, apply_asymmetric_volt: false,
      apply_asymmetric_volt_dev: true, apply_asymmetric_freq_dev: true,
      // ISO 8528-5 dual-band: β_f start band (±0.25% of nom) + α_f stop band (±1% of nom).
      iso_8528_5_mode: true, band_mode: 'pct', beta_f_pct: 0.5, alpha_f_pct: 2.0,
      // Abs values at 50 Hz nominal (resolver recomputes for other nominal frequencies).
      freq_start_upper_increase: 50.125, freq_start_lower_increase: 49.875,
      freq_start_upper_decrease: 50.125, freq_start_lower_decrease: 49.875,
      f_stop_upper: 50.5, f_stop_lower: 49.5,
    },
  },
  {
    name: 'ISO 8528 G2',
    values: {
      voltage_tolerance_pct: 5.0, voltage_recovery_time_s: 6.0,
      voltage_max_deviation_pct: 20, volt_max_dev_pct_increase: 20, volt_max_dev_pct_decrease: 25,
      frequency_tolerance_pct: 0.5, frequency_recovery_time_s: 5.0,
      frequency_max_deviation_pct: 10, freq_max_dev_pct_increase: 10, freq_max_dev_pct_decrease: 12,
      freq_recovery_upper_increase: 51.5, freq_recovery_lower_increase: 48.75,
      freq_recovery_upper_decrease: 51.25, freq_recovery_lower_decrease: 48.5,
      apply_asymmetric_freq: true, apply_asymmetric_volt: false,
      apply_asymmetric_volt_dev: true, apply_asymmetric_freq_dev: true,
      // ISO 8528-5 dual-band: β_f ±0.75% (1.5%), α_f ±1% (2.0%).
      iso_8528_5_mode: true, band_mode: 'pct', beta_f_pct: 1.5, alpha_f_pct: 2.0,
      freq_start_upper_increase: 50.375, freq_start_lower_increase: 49.625,
      freq_start_upper_decrease: 50.375, freq_start_lower_decrease: 49.625,
      f_stop_upper: 50.5, f_stop_lower: 49.5,
    },
  },
  {
    name: 'ISO 8528 G1',
    values: {
      voltage_tolerance_pct: 10.0, voltage_recovery_time_s: 10.0,
      voltage_max_deviation_pct: 25, volt_max_dev_pct_increase: 25, volt_max_dev_pct_decrease: 30,
      frequency_tolerance_pct: 0.5, frequency_recovery_time_s: 10.0,
      frequency_max_deviation_pct: 15, freq_max_dev_pct_increase: 15, freq_max_dev_pct_decrease: 18,
      freq_recovery_upper_increase: 51.5, freq_recovery_lower_increase: 48.75,
      freq_recovery_upper_decrease: 51.25, freq_recovery_lower_decrease: 48.5,
      apply_asymmetric_freq: true, apply_asymmetric_volt: false,
      apply_asymmetric_volt_dev: true, apply_asymmetric_freq_dev: true,
      // ISO 8528-5 dual-band: β_f ±1.25% (2.5%), α_f ±1.75% (3.5%).
      iso_8528_5_mode: true, band_mode: 'pct', beta_f_pct: 2.5, alpha_f_pct: 3.5,
      freq_start_upper_increase: 50.625, freq_start_lower_increase: 49.375,
      freq_start_upper_decrease: 50.625, freq_start_lower_decrease: 49.375,
      f_stop_upper: 50.875, f_stop_lower: 49.125,
    },
  },
];

/**
 * Port of Streamlit's _resolve_iso_freq_bands (app.py ~166–208).
 *
 * Returns the resolved α_f recovery/stop band and β_f start band for the engine.
 * In ISO mode the two bands are distinct; outside ISO mode the start band collapses
 * to equal the recovery band so the engine sees a single-band stopwatch.
 */
function resolveIsoFreqBands(c: AnalysisConfigInput, fSymUp: number, fSymLo: number): {
  recUpInc: number; recLoInc: number; recUpDec: number; recLoDec: number;
  startUpInc: number; startLoInc: number; startUpDec: number; startLoDec: number;
} {
  if (!c.iso_8528_5_mode) {
    // Non-ISO path: keep existing asymmetric/symmetric logic; start band = rec band.
    const recUpInc = c.apply_asymmetric_freq ? c.freq_recovery_upper_increase : fSymUp;
    const recLoInc = c.apply_asymmetric_freq ? c.freq_recovery_lower_increase : fSymLo;
    const recUpDec = c.apply_asymmetric_freq ? c.freq_recovery_upper_decrease : fSymUp;
    const recLoDec = c.apply_asymmetric_freq ? c.freq_recovery_lower_decrease : fSymLo;
    return { recUpInc, recLoInc, recUpDec, recLoDec,
             startUpInc: recUpInc, startLoInc: recLoInc, startUpDec: recUpDec, startLoDec: recLoDec };
  }
  // ISO mode: compute symmetric β_f and α_f bands (same for increase and decrease).
  let startUp: number, startLo: number, stopUp: number, stopLo: number;
  if (c.band_mode === 'pct') {
    const bfHalf = (c.beta_f_pct / 2) / 100 * c.nominal_frequency;
    const afHalf = (c.alpha_f_pct / 2) / 100 * c.nominal_frequency;
    startUp = c.nominal_frequency + bfHalf;
    startLo = c.nominal_frequency - bfHalf;
    stopUp  = c.nominal_frequency + afHalf;
    stopLo  = c.nominal_frequency - afHalf;
  } else {
    startUp = c.freq_start_upper_increase;
    startLo = c.freq_start_lower_increase;
    stopUp  = c.f_stop_upper;
    stopLo  = c.f_stop_lower;
  }
  return {
    recUpInc: stopUp,  recLoInc: stopLo,  recUpDec: stopUp,  recLoDec: stopLo,
    startUpInc: startUp, startLoInc: startLo, startUpDec: startUp, startLoDec: startLo,
  };
}

/**
 * Resolve the raw sidebar inputs into the engine's AnalysisConfig dict, applying
 * the same asymmetric logic as app.py: when a toggle is off the band/limit is
 * symmetric (derived from the tolerance % around nominal); when on the explicit
 * per-direction values are used. Only engine fields are emitted — display flags,
 * rated load and expected steps stay client-side.
 */
export function resolveConfig(c: AnalysisConfigInput): Record<string, number | string | boolean> {
  const vUp = c.nominal_voltage * (1 + c.voltage_tolerance_pct / 100);
  const vLo = c.nominal_voltage * (1 - c.voltage_tolerance_pct / 100);
  const fUp = c.nominal_frequency * (1 + c.frequency_tolerance_pct / 100);
  const fLo = c.nominal_frequency * (1 - c.frequency_tolerance_pct / 100);
  const iso = resolveIsoFreqBands(c, fUp, fLo);
  return {
    nominal_voltage: c.nominal_voltage,
    nominal_frequency: c.nominal_frequency,
    ln_to_ll_mode: c.ln_to_ll_mode,
    load_threshold_kw: c.load_threshold_kw,
    detection_window_s: c.detection_window_s,
    snapshot_window_s: c.snapshot_window_s,
    recovery_verify_s: c.recovery_verify_s,
    fault_recovery_threshold_s: c.fault_recovery_threshold_s,
    voltage_tolerance_pct: c.voltage_tolerance_pct,
    voltage_recovery_time_s: c.voltage_recovery_time_s,
    voltage_max_deviation_pct: c.voltage_max_deviation_pct,
    frequency_tolerance_pct: c.frequency_tolerance_pct,
    frequency_recovery_time_s: c.frequency_recovery_time_s,
    frequency_max_deviation_pct: c.frequency_max_deviation_pct,
    volt_recovery_upper_increase: c.apply_asymmetric_volt ? c.volt_recovery_upper_increase : vUp,
    volt_recovery_lower_increase: c.apply_asymmetric_volt ? c.volt_recovery_lower_increase : vLo,
    volt_recovery_upper_decrease: c.apply_asymmetric_volt ? c.volt_recovery_upper_decrease : vUp,
    volt_recovery_lower_decrease: c.apply_asymmetric_volt ? c.volt_recovery_lower_decrease : vLo,
    // Frequency recovery (α_f stop) band: resolved by ISO resolver so ISO mode
    // always wins over the asymmetric toggle.
    freq_recovery_upper_increase: iso.recUpInc,
    freq_recovery_lower_increase: iso.recLoInc,
    freq_recovery_upper_decrease: iso.recUpDec,
    freq_recovery_lower_decrease: iso.recLoDec,
    volt_max_dev_pct_increase: c.apply_asymmetric_volt_dev ? c.volt_max_dev_pct_increase : c.voltage_max_deviation_pct,
    volt_max_dev_pct_decrease: c.apply_asymmetric_volt_dev ? c.volt_max_dev_pct_decrease : c.voltage_max_deviation_pct,
    freq_max_dev_pct_increase: c.apply_asymmetric_freq_dev ? c.freq_max_dev_pct_increase : c.frequency_max_deviation_pct,
    freq_max_dev_pct_decrease: c.apply_asymmetric_freq_dev ? c.freq_max_dev_pct_decrease : c.frequency_max_deviation_pct,
    // ISO 8528-5 mode flag + β_f start band (engine uses these when iso_8528_5_mode=True).
    iso_8528_5_mode: c.iso_8528_5_mode,
    freq_start_upper_increase: iso.startUpInc,
    freq_start_lower_increase: iso.startLoInc,
    freq_start_upper_decrease: iso.startUpDec,
    freq_start_lower_decrease: iso.startLoDec,
    // Steady-state δ-band evaluation (opt-in). rated_load_kw is only emitted
    // when set so the engine leaves dwell load-% blank rather than dividing by 0.
    steady_state_enabled: c.steady_state_enabled,
    steady_voltage_band_pct: c.steady_voltage_band_pct,
    steady_freq_band_pct: c.steady_freq_band_pct,
    steady_dwell_min_s: c.steady_dwell_min_s,
    steady_exclusion_s: c.steady_exclusion_s,
    // ISO 8528-5 Table 4 grading. The class is only emitted when set so the
    // engine falls back to legacy δ-band mode (null is dropped host-side).
    steady_isochronous: c.steady_isochronous,
    steady_single_two_cylinder: c.steady_single_two_cylinder,
    steady_low_power: c.steady_low_power,
    steady_parallel_operation: c.steady_parallel_operation,
    ...(c.steady_performance_class != null
      ? { steady_performance_class: c.steady_performance_class } : {}),
    ...(c.rated_load_kw != null ? { rated_load_kw: c.rated_load_kw } : {}),
  };
}

/** Display flags + reporting helpers, for SnapshotChart and report image options. */
export interface DisplayOptions {
  show_limits: boolean;
  show_tolerance_band: boolean;
  show_deviation_limits: boolean;
  show_intersections: boolean;
  show_max_deviation: boolean;
  rated_load_kw: number | null;
}

export function displayOptions(c: AnalysisConfigInput): DisplayOptions {
  // The master `show_data_points` toggle gates the four snapshot-marker flags.
  const dp = c.show_data_points;
  return {
    show_limits: c.show_limits,
    show_tolerance_band: dp && c.show_tolerance_band,
    show_deviation_limits: dp && c.show_deviation_limits,
    show_intersections: dp && c.show_intersections,
    show_max_deviation: dp && c.show_max_deviation,
    rated_load_kw: c.rated_load_kw,
  };
}

const STORAGE_KEY = 'pqa.config.v2';

export function loadConfig(): AnalysisConfigInput {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...DEFAULT_CONFIG, ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return { ...DEFAULT_CONFIG };
}

export function saveConfig(config: AnalysisConfigInput): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  } catch {
    /* ignore */
  }
}
