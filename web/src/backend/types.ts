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
