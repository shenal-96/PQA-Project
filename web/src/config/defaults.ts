// Analysis configuration mirrored from core/analysis.py AnalysisConfig, plus the
// built-in ISO 8528 presets (from CLAUDE.md). The config object is sent to the
// backend's runAnalysis(); only fields the engine knows are applied host-side.

export type LnToLlMode = 'auto' | 'force_ll' | 'force_ln';

export interface AnalysisConfigInput {
  nominal_voltage: number;
  nominal_frequency: number;
  load_threshold_kw: number;
  detection_window_s: number;
  snapshot_window_s: number;
  recovery_verify_s: number;
  fault_recovery_threshold_s: number;
  ln_to_ll_mode: LnToLlMode;
  voltage_tolerance_pct: number;
  voltage_recovery_time_s: number;
  frequency_tolerance_pct: number;
  frequency_recovery_time_s: number;
  // asymmetric frequency recovery bands (absolute Hz)
  freq_recovery_upper_increase: number;
  freq_recovery_lower_increase: number;
  freq_recovery_upper_decrease: number;
  freq_recovery_lower_decrease: number;
  // asymmetric max-deviation limits (%)
  volt_max_dev_pct_increase: number;
  volt_max_dev_pct_decrease: number;
  freq_max_dev_pct_increase: number;
  freq_max_dev_pct_decrease: number;
}

export const DEFAULT_CONFIG: AnalysisConfigInput = {
  nominal_voltage: 415,
  nominal_frequency: 50,
  load_threshold_kw: 50,
  detection_window_s: 5,
  snapshot_window_s: 10,
  recovery_verify_s: 6,
  fault_recovery_threshold_s: 10,
  ln_to_ll_mode: 'auto',
  voltage_tolerance_pct: 1.0,
  voltage_recovery_time_s: 4.0,
  frequency_tolerance_pct: 0.5,
  frequency_recovery_time_s: 3.0,
  freq_recovery_upper_increase: 50.5,
  freq_recovery_lower_increase: 49.75,
  freq_recovery_upper_decrease: 50.25,
  freq_recovery_lower_decrease: 49.5,
  volt_max_dev_pct_increase: 15,
  volt_max_dev_pct_decrease: 15,
  freq_max_dev_pct_increase: 7,
  freq_max_dev_pct_decrease: 7,
};

export const VOLTAGE_PRESETS = [415, 690, 11000];

export interface Preset {
  name: string;
  values: Partial<AnalysisConfigInput>;
}

// Built-in ISO 8528 presets (seed values from CLAUDE.md "Preset Configurator").
export const BUILTIN_PRESETS: Preset[] = [
  {
    name: 'ISO 8528 G3',
    values: {
      voltage_tolerance_pct: 1.0, voltage_recovery_time_s: 4.0,
      volt_max_dev_pct_increase: 15, volt_max_dev_pct_decrease: 20,
      frequency_tolerance_pct: 0.5, frequency_recovery_time_s: 3.0,
      freq_max_dev_pct_increase: 7, freq_max_dev_pct_decrease: 10,
      freq_recovery_upper_increase: 50.5, freq_recovery_lower_increase: 49.75,
      freq_recovery_upper_decrease: 50.25, freq_recovery_lower_decrease: 49.5,
    },
  },
  {
    name: 'ISO 8528 G2',
    values: {
      voltage_tolerance_pct: 5.0, voltage_recovery_time_s: 6.0,
      volt_max_dev_pct_increase: 20, volt_max_dev_pct_decrease: 25,
      frequency_tolerance_pct: 0.5, frequency_recovery_time_s: 5.0,
      freq_max_dev_pct_increase: 10, freq_max_dev_pct_decrease: 12,
      freq_recovery_upper_increase: 51.5, freq_recovery_lower_increase: 48.75,
      freq_recovery_upper_decrease: 51.25, freq_recovery_lower_decrease: 48.5,
    },
  },
  {
    name: 'ISO 8528 G1',
    values: {
      voltage_tolerance_pct: 10.0, voltage_recovery_time_s: 10.0,
      volt_max_dev_pct_increase: 25, volt_max_dev_pct_decrease: 30,
      frequency_tolerance_pct: 0.5, frequency_recovery_time_s: 10.0,
      freq_max_dev_pct_increase: 15, freq_max_dev_pct_decrease: 18,
      freq_recovery_upper_increase: 51.5, freq_recovery_lower_increase: 48.75,
      freq_recovery_upper_decrease: 51.25, freq_recovery_lower_decrease: 48.5,
    },
  },
];

const STORAGE_KEY = 'pqa.config.v1';

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
