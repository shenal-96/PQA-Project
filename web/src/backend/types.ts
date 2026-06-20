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

export interface AnalysisResult {
  logger_format: string | null;
  n_rows: number;
  events: EventRecord[];
  metrics: Record<string, MetricSeries>;
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

// Per-event override (matches core.recalc / app.py intersection_overrides).
export interface EventOverride {
  v_exit_offset?: number;
  v_rec_override?: number | null;
  f_exit_offset?: number;
  f_rec_override?: number | null;
}
