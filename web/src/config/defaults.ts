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
  // start band and STOPS when it re-enters the α_f stop band (the freq recovery
  // bands above). Also enables the §7 pre/post steady-state checks.
  iso_8528_5_mode: boolean;
  freq_start_upper_increase: number;
  freq_start_lower_increase: number;
  freq_start_upper_decrease: number;
  freq_start_lower_decrease: number;

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
  freq_start_upper_increase: 50.25,
  freq_start_lower_increase: 49.75,
  freq_start_upper_decrease: 50.25,
  freq_start_lower_decrease: 49.75,

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
  show_tolerance_band: true,
  show_deviation_limits: true,
  show_intersections: false,
  show_max_deviation: false,

  steady_state_enabled: false,
  steady_voltage_band_pct: 2.5,
  steady_freq_band_pct: 2.0,
  steady_dwell_min_s: 30,
  steady_exclusion_s: 10,

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
      freq_recovery_upper_increase: 50.5, freq_recovery_lower_increase: 49.75,
      freq_recovery_upper_decrease: 50.25, freq_recovery_lower_decrease: 49.5,
      apply_asymmetric_freq: true, apply_asymmetric_volt: false,
      apply_asymmetric_volt_dev: true, apply_asymmetric_freq_dev: true,
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
    },
  },
];

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
    freq_recovery_upper_increase: c.apply_asymmetric_freq ? c.freq_recovery_upper_increase : fUp,
    freq_recovery_lower_increase: c.apply_asymmetric_freq ? c.freq_recovery_lower_increase : fLo,
    freq_recovery_upper_decrease: c.apply_asymmetric_freq ? c.freq_recovery_upper_decrease : fUp,
    freq_recovery_lower_decrease: c.apply_asymmetric_freq ? c.freq_recovery_lower_decrease : fLo,
    volt_max_dev_pct_increase: c.apply_asymmetric_volt_dev ? c.volt_max_dev_pct_increase : c.voltage_max_deviation_pct,
    volt_max_dev_pct_decrease: c.apply_asymmetric_volt_dev ? c.volt_max_dev_pct_decrease : c.voltage_max_deviation_pct,
    freq_max_dev_pct_increase: c.apply_asymmetric_freq_dev ? c.freq_max_dev_pct_increase : c.frequency_max_deviation_pct,
    freq_max_dev_pct_decrease: c.apply_asymmetric_freq_dev ? c.freq_max_dev_pct_decrease : c.frequency_max_deviation_pct,
    // ISO 8528-5 dual frequency bands: β_f start band (engine reads these only
    // when iso_8528_5_mode is on; the α_f stop band is the freq recovery band).
    iso_8528_5_mode: c.iso_8528_5_mode,
    freq_start_upper_increase: c.freq_start_upper_increase,
    freq_start_lower_increase: c.freq_start_lower_increase,
    freq_start_upper_decrease: c.freq_start_upper_decrease,
    freq_start_lower_decrease: c.freq_start_lower_decrease,
    // Steady-state δ-band evaluation (opt-in). rated_load_kw is only emitted
    // when set so the engine leaves dwell load-% blank rather than dividing by 0.
    steady_state_enabled: c.steady_state_enabled,
    steady_voltage_band_pct: c.steady_voltage_band_pct,
    steady_freq_band_pct: c.steady_freq_band_pct,
    steady_dwell_min_s: c.steady_dwell_min_s,
    steady_exclusion_s: c.steady_exclusion_s,
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
  return {
    show_limits: c.show_limits,
    show_tolerance_band: c.show_tolerance_band,
    show_deviation_limits: c.show_deviation_limits,
    show_intersections: c.show_intersections,
    show_max_deviation: c.show_max_deviation,
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
