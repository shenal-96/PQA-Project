import type {
  AnalysisResult, Caps, CrashReportResult, CsvMeta, EcuRecording, EventOverride,
  EventRecord, IticData, MetricSeries, PendingCrashStatus, ReportRequest,
  ReportResult, SaveResult, SetpointOptions, SetpointResult, SettingsReference,
  SnapshotData, SnapshotOpts, SteadyResult, SteadyWindowEdit, TemplateInfo,
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
  /** Load a WinScope .xls/.xlsx export (desktop, gated on caps.canXls). */
  loadWinscope?(file: File): Promise<CsvMeta>;
  runAnalysis(config?: Record<string, unknown>): Promise<AnalysisResult>;
  metricSeries(column: string): Promise<MetricSeries>;
  /** 4-panel snapshot for one event (by positional index). */
  snapshot(index: number, opts?: SnapshotOpts): Promise<SnapshotData>;
  /** Apply per-event overrides and re-run compliance; returns updated events. */
  recalc(overrides: Record<number, EventOverride>): Promise<{ events: EventRecord[]; itic?: IticData }>;
  /**
   * Re-evaluate steady-state (ISO 8528-5 δ bands) for user-confirmed/edited
   * dwell windows. Omit `windows` to re-detect them automatically.
   */
  recalcSteady?(windows?: SteadyWindowEdit[]): Promise<SteadyResult>;

  // ---- reports (gated on caps.canReport) -------------------------------------
  /** Build report artifacts (PDF/HTML/.docx) from the last analysis. */
  generateReport(req: ReportRequest): Promise<ReportResult>;
  /** The built-in editable HTML report template. */
  defaultHtmlTemplate(): Promise<string>;

  // ---- Word template library (desktop only, gated on caps.canReport) ---------
  /** List the persisted Word templates with size + snapshot-slot metadata. */
  listTemplates?(): Promise<TemplateInfo[]>;
  /** Persist an uploaded ``.docx`` template; returns the updated library. */
  saveTemplate?(file: File): Promise<TemplateInfo[]>;
  /** Remove a stored template by name; returns the updated library. */
  deleteTemplate?(name: string): Promise<TemplateInfo[]>;

  // ---- XLS tabs (gated on caps.canXls) ---------------------------------------
  /** Diff 2+ ECU parameter files (XLS/XLSX or ComAp CSV). */
  compareSetpoint?(kind: 'xls' | 'csv', files: File[], options?: SetpointOptions): Promise<SetpointResult>;
  /** Read an ECU recording XLS/XLSX into grouped time series. */
  ecuRecording?(file: File): Promise<EcuRecording>;
  /** Curated ComAp/D550 settings knowledge base (no XLS gating — UI-free data). */
  settingsReference?(): Promise<SettingsReference>;
  /**
   * Optional native "Save As" (desktop only). When absent the UI falls back to a
   * browser blob download. `dataB64` is the file's base64 bytes.
   */
  saveFile?(filename: string, dataB64: string): Promise<SaveResult>;

  // ---- crash reporting (desktop only) ---------------------------------------
  /** Whether a prior session crashed without the report being sent. */
  pendingCrash?(): Promise<PendingCrashStatus>;
  /** Open the user's mail client pre-addressed to the developer with the report. */
  emailCrashReport?(): Promise<CrashReportResult>;
  /** Clear the pending-crash marker without emailing (user declined). */
  dismissCrashReport?(): Promise<void>;
}
