import type {
  AnalysisResult, Caps, CsvMeta, EventOverride, EventRecord,
  MetricSeries, ReportRequest, ReportResult, SaveResult,
  SnapshotData, SnapshotOpts,
} from './types';

/**
 * The single seam between the UI and "where analysis runs".
 *
 * UI components depend ONLY on this interface, never on `window.pywebview` or
 * any runtime directly. Today the implementation is `PyWebviewBackend` (Windows,
 * in-process host Python); the future iPad app adds a `PyodideBackend` (in-browser
 * WASM) with no UI changes.
 */
export interface AnalysisBackend {
  caps(): Promise<Caps>;
  loadCsv(file: File): Promise<CsvMeta>;
  runAnalysis(config?: Record<string, unknown>): Promise<AnalysisResult>;
  metricSeries(column: string): Promise<MetricSeries>;
  /** 4-panel snapshot for one event (by positional index). */
  snapshot(index: number, opts?: SnapshotOpts): Promise<SnapshotData>;
  /** Apply per-event overrides and re-run compliance; returns updated events. */
  recalc(overrides: Record<number, EventOverride>): Promise<{ events: EventRecord[] }>;

  // ---- reports (gated on caps.canReport) -------------------------------------
  /** Build report artifacts (PDF/HTML/.docx) from the last analysis. */
  generateReport(req: ReportRequest): Promise<ReportResult>;
  /** The built-in editable HTML report template. */
  defaultHtmlTemplate(): Promise<string>;
  /**
   * Optional native "Save As" (desktop only). When absent the UI falls back to a
   * browser blob download. `dataB64` is the file's base64 bytes.
   */
  saveFile?(filename: string, dataB64: string): Promise<SaveResult>;
}
