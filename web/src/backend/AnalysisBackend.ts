import type { AnalysisResult, Caps, CsvMeta, MetricSeries } from './types';

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
}
