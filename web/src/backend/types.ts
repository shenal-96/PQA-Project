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
  Hunting: boolean;
  Hunting_Reasons: string;
  Status: 'Pass' | 'Fail';
  Failure_Reasons: string;
}

/** A user-confirmed/edited dwell window sent back to recalcSteady. */
export interface SteadyWindowEdit {
  start: string;
  end: string;
  label?: string | null;
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
  rated_load_kw?: number | null;
  image_options?: Record<string, unknown>;
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

// --- Set Point comparison (M4) -------------------------------------------------
export type SetpointKind = 'xls' | 'csv';
export interface SetpointFile {
  filename: string;
  b64: string;
}
export interface SetpointResult {
  kind: SetpointKind;
  columns: string[];
  labels: string[];
  rows: Array<Record<string, string | number | boolean | null>>;
  n_files: number;
  n_diffs: number;
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
