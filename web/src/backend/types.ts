// TypeScript mirror of the JSON contract produced by core/serialize.py.
// Every backend (PyWebview now, Pyodide later) returns exactly these shapes.

export type Platform = 'desktop' | 'pwa' | 'mock';

export interface Caps {
  platform: Platform;
  canReport: boolean;
  canXls: boolean;
}

export interface CsvMeta {
  filename?: string | null;
  logger_format: string | null;
  n_rows: number;
  columns: string[];
  /** ISO datetimes of the first/last sample, for seeding the time-window picker. */
  time_min?: string | null;
  time_max?: string | null;
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface MetricSeries {
  column: string;
  timestamps: Array<string | number>;
  values: Array<number | null>;
}

export type EventRecord = Record<string, string | number | boolean | null>;

// ITIC / CBEMA curve (from core/viz_dataprep.itic_curve).
export interface IticEvent {
  dur: number;
  pct: number;
  inside: boolean;
}
export interface IticData {
  upper: number[][];   // [[duration_s, percent], ...] stepped envelope
  lower: number[][];
  events: IticEvent[];
  x_min: number;
  x_max: number;
  y_max: number;
}

// One detected-event marker for the kW 'Detected Events' overlay
// (core/viz_dataprep.detected_events_overlay).
export interface EventOverlayMarker {
  timestamp: string | number | null;
  dKw: number | null;
  label: string;
}

// One steady-state dwell window evaluated against the ISO 8528-5 δ bands
// (core/analysis.evaluate_steady_window). Distinct from transient EventRecord.
export interface SteadyWindow {
  Window_Index: number;
  Start_Timestamp: string;
  End_Timestamp: string;
  Duration_s: number;
  n_samples: number;
  Mean_kW: number | null;
  Load_Pct: number | null;
  Load_Label: string | null;
  V_band_lower: number; V_band_upper: number;
  V_min: number | null; V_max: number | null; V_mean: number | null;
  V_n_out: number; V_pct_out: number | null; V_worst_dev_pct: number | null;
  F_band_lower: number; F_band_upper: number;
  F_min: number | null; F_max: number | null; F_mean: number | null;
  F_n_out: number; F_pct_out: number | null; F_worst_dev_pct: number | null;
  // β_f — steady-state frequency band (peak-to-peak / f_r, spec §2.1). Always
  // reported; limit/pass populated only when a performance class is selected.
  Beta_f_pct: number | null;
  Beta_f_limit_pct: number | null;
  Beta_f_pass: boolean | null;
  Hunting: boolean;
  Hunting_Reasons: string;
  Status: 'Pass' | 'Fail';
  Failure_Reasons: string;
}

/** Cross-window ISO 8528-5 steady-state metrics (core.analysis.summarize_steady_state).
 * Aggregates the per-window dwell rows into the no-load → rated sweep metrics. */
export interface SteadySummary {
  performance_class: 'G1' | 'G2' | 'G3' | null;
  limits: Record<string, number | null> | null;
  n_windows: number;
  sample_rate_hz: number | null;
  // ΔU_st — voltage regulation band (§2.3)
  delta_u_st_pct: number | null;
  delta_u_st_limit_pct: number | null;
  delta_u_st_pass: boolean | null;
  u_st_min_v: number | null;
  u_st_max_v: number | null;
  // Frequency droop sanity (§3.3) — ≈ 0 for an isochronous set
  freq_droop_pct: number | null;
  freq_droop_limit_pct: number | null;
  freq_droop_pass: boolean | null;
  // ΔU_2.0 voltage unbalance @ no-load (§2.4) — deferred; carries gate status
  volt_unbalance_pct: number | null;
  volt_unbalance_limit_pct: number | null;
  volt_unbalance_pass: boolean | null;
  volt_unbalance_status: string;
  // Û_mod,s voltage modulation (§2.5) — gated on sample rate (§4)
  modulation_pct: number | null;
  modulation_limit_pct: number | null;
  modulation_pass: boolean | null;
  modulation_status: string;
}

/** A user-confirmed/edited dwell window sent back to recalcSteady. */
export interface SteadyWindowEdit {
  start: string;
  end: string;
  label?: string | null;
}

/** recalcSteady return shape: per-window rows + the cross-window summary. */
export interface SteadyResult {
  steady: SteadyWindow[];
  steady_summary?: SteadySummary;
}

export interface AnalysisResult {
  logger_format: string | null;
  n_rows: number;
  events: EventRecord[];
  metrics: Record<string, MetricSeries>;
  itic?: IticData;
  events_overlay?: EventOverlayMarker[];
  // Present only when steady_state_enabled (ISO 8528-5 δ-band evaluation).
  steady?: SteadyWindow[];
  // Cross-window steady-state summary (ΔU_st, droop, sample-rate gate, class).
  steady_summary?: SteadySummary;
}

// --- Event snapshots -----------------------------------------------------------
export interface SnapshotMarker {
  ts: string | null;
  value: number | null;
  rec_s?: number;
}
export interface SnapshotBand {
  upper: number;
  lower: number;
}
export interface SnapshotLimit {
  value: number;
  side: 'upper' | 'lower';
  pct: number;
}
export interface SnapshotPanel {
  label: string;
  color: string;
  column: string;
  timestamps: Array<string | number>;
  values: Array<number | null>;
  band?: SnapshotBand;
  start_band?: SnapshotBand;   // ISO 8528-5 β_f start band (frequency only)
  limit?: SnapshotLimit;
  exit?: SnapshotMarker;
  recovery?: SnapshotMarker;
  extreme?: SnapshotMarker;
  not_recovered?: boolean;
}
export interface SnapshotData {
  event_index: number | null;
  event_ts: string | null;
  window_s: number;
  left_s: number;
  right_s: number;
  time_offset_s: number;
  dKw: number;
  direction: 'increase' | 'decrease';
  panels: {
    voltage: SnapshotPanel;
    current: SnapshotPanel;
    frequency: SnapshotPanel;
    power: SnapshotPanel;
  };
}
export interface SnapshotOpts {
  window_s?: number;
  time_offset_s?: number;
}

// --- Reports (M3) --------------------------------------------------------------
// Mirror of desktop/report_host.build_report's params + return shape.
export interface ReportFields {
  report_title: string;
  pqa_serial: string;
  gen_sn: string;
  site_address: string;
  custom_text: string;
}
export interface ReportOutputs {
  pdf: boolean;
  html: boolean;
  docx: boolean;
}
export interface ReportRequest {
  fields: ReportFields;
  filename: string;
  outputs: ReportOutputs;
  html_template?: string;
  docx_template_b64?: string;
  /** Name of a template in the persistent library (alternative to inline b64). */
  docx_template_name?: string;
  /** Drop the not-recovered watermark/tint from the report snapshots. */
  clear_not_recovered?: boolean;
  /** Add the compliance summary table, even when the template has no placeholder. */
  include_compliance_table?: boolean;
  /** Render + add the ITIC (CBEMA) curve to the report. */
  include_itic?: boolean;
  rated_load_kw?: number | null;
  image_options?: Record<string, unknown>;
  /** Per-event snapshot window-size (s) overrides, keyed by event index. */
  snapshot_window_overrides?: Record<number, number>;
  /** Per-event snapshot time-shift (s) overrides, keyed by event index. */
  snapshot_offset_overrides?: Record<number, number>;
}
/** One stored Word template in the persistent library. */
export interface TemplateInfo {
  name: string;
  size: number;
  /** Indices N of every {{Snapshot_N}} placeholder found in the template. */
  snapshot_indices: number[];
  snapshot_max: number;
}
export interface ReportArtifacts {
  pdf_b64?: string | null;
  html?: string | null;
  docx_b64?: string | null;
  docx_mime?: string | null;
}
export interface ReportResult {
  filename: string;
  artifacts: ReportArtifacts;
  pdf_ok: boolean;
  warnings: string[];
  log: string;
}
/** Result of a native Save-As dialog (desktop only). */
export interface SaveResult {
  path: string | null;
  error?: string;
}
/** Result of saving several report artifacts via ONE native Save dialog. */
export interface SaveManyResult {
  /** Absolute paths written (empty if the user cancelled). */
  paths: string[];
  error?: string;
}

// --- Set Point comparison (M4) -------------------------------------------------
export type SetpointKind = 'xls' | 'csv';
export interface SetpointFile {
  filename: string;
  b64: string;
}
export interface SetpointOptions {
  hide_unchanged?: boolean;
  ignore_whitespace?: boolean;
  ignore_case?: boolean;
}
export interface SetpointResult {
  kind: SetpointKind;
  columns: string[];
  labels: string[];
  rows: Array<Record<string, string | number | boolean | null>>;
  n_files: number;
  n_diffs: number;
  /** Diffchecker-style side-by-side HTML view (desktop only; absent on MockBackend). */
  html?: string;
}

// --- ECU recording (M4) --------------------------------------------------------
export interface EcuRecording {
  filename: string;
  n_rows: number;
  timestamps: Array<string | number>;
  channels: Record<string, Array<number | null>>;
  groups: Record<string, string[]>;
  labels: Record<string, string>;
}

// Per-event override (matches core.recalc / app.py intersection_overrides).
export interface EventOverride {
  v_exit_offset?: number;
  v_rec_override?: number | null;
  f_exit_offset?: number;
  f_rec_override?: number | null;
}

// --- Crash reporting (desktop only) --------------------------------------------
/** Summary of an unreported crash from a prior session. */
export interface PendingCrash {
  timestamp: string;
  user: string;
  error_type: string;
  message: string;
  context: string;
}
export interface PendingCrashStatus {
  pending: PendingCrash | null;
  email: string;
}
/** Result of opening the mail client with the crash report. */
export interface CrashReportResult {
  ok: boolean;
  email: string;
  report_path: string | null;
  mailto_opened: boolean;
  revealed: boolean;
  error?: string | null;
}

// --- In-app feedback (feature request / bug report) ----------------------------
/** Which kind of feedback the user is sending from the changelog dialog. */
export type FeedbackKind = 'feature' | 'bug';
/** Result of opening the mail client with a feature request / bug report. */
export interface FeedbackResult {
  ok: boolean;
  email: string;
  mailto_opened: boolean;
  error?: string | null;
}

// --- Settings Reference (curated ComAp/D550 knowledge base) ---------------------
/** One setpoint/parameter entry with plain-English context. */
export interface ReferenceSetting {
  name: string;
  units: string;
  range: string;
  default: string;
  description: string;
  philosophy: string;
  performance: string;
}
/** A named group of settings within a device. */
export interface ReferenceGroup {
  name: string;
  settings: ReferenceSetting[];
}
/** One device (controller/AVR) with its grouped settings. */
export interface ReferenceDevice {
  name: string;
  summary: string;
  source: string;
  /** True once the data has been verified against the official manual. */
  verified: boolean;
  groups: ReferenceGroup[];
}
/** The full curated settings reference returned over the bridge. */
export interface SettingsReference {
  devices: ReferenceDevice[];
  count: number;
}
