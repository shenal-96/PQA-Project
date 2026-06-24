import type { AnalysisBackend } from './AnalysisBackend';
import type {
  AnalysisResult, Caps, CrashReportResult, CsvMeta, EcuRecording, EventOverride,
  EventRecord, IticData, MetricSeries, PendingCrashStatus, ReportRequest,
  ReportResult, SaveResult, SetpointOptions, SetpointResult, SnapshotData, SnapshotOpts,
  SteadyWindow, SteadyWindowEdit,
} from './types';

declare global {
  interface Window {
    pywebview?: { api: Record<string, (...args: unknown[]) => Promise<unknown>> };
  }
}

/** Read a File as base64 (no data: prefix) for binary-safe transfer over the bridge. */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => {
      const res = reader.result as string;
      resolve(res.slice(res.indexOf(',') + 1));
    };
    reader.readAsDataURL(file);
  });
}

/**
 * Windows desktop backend: calls host Python through PyWebview's in-process
 * bridge (`window.pywebview.api.*`). No HTTP, no network — direct function calls
 * inside the same process.
 */
export class PyWebviewBackend implements AnalysisBackend {
  private get api() {
    const api = window.pywebview?.api;
    if (!api) throw new Error('PyWebview bridge is not available');
    return api;
  }

  caps(): Promise<Caps> {
    return this.api.caps() as Promise<Caps>;
  }

  async loadCsv(file: File): Promise<CsvMeta> {
    const csv_b64 = await fileToBase64(file);
    return this.api.load_csv({ csv_b64, filename: file.name }) as Promise<CsvMeta>;
  }

  async loadWinscope(file: File): Promise<CsvMeta> {
    const b64 = await fileToBase64(file);
    return this.api.load_winscope({ b64, filename: file.name }) as Promise<CsvMeta>;
  }

  async compareSetpoint(kind: 'xls' | 'csv', files: File[], options?: SetpointOptions): Promise<SetpointResult> {
    const payload = await Promise.all(
      files.map(async (f) => ({ filename: f.name, b64: await fileToBase64(f) })),
    );
    return this.api.compare_setpoint({ kind, files: payload, options: options ?? {} }) as Promise<SetpointResult>;
  }

  async ecuRecording(file: File): Promise<EcuRecording> {
    const b64 = await fileToBase64(file);
    return this.api.ecu_recording({ b64, filename: file.name }) as Promise<EcuRecording>;
  }

  runAnalysis(config: Record<string, unknown> = {}): Promise<AnalysisResult> {
    return this.api.run_analysis(config) as Promise<AnalysisResult>;
  }

  metricSeries(column: string): Promise<MetricSeries> {
    return this.api.metric_series(column) as Promise<MetricSeries>;
  }

  snapshot(index: number, opts: SnapshotOpts = {}): Promise<SnapshotData> {
    return this.api.snapshot({ index, ...opts }) as Promise<SnapshotData>;
  }

  recalc(overrides: Record<number, EventOverride>): Promise<{ events: EventRecord[]; itic?: IticData }> {
    return this.api.recalc({ overrides }) as Promise<{ events: EventRecord[]; itic?: IticData }>;
  }

  recalcSteady(windows?: SteadyWindowEdit[]): Promise<{ steady: SteadyWindow[] }> {
    return this.api.recalc_steady(windows ? { windows } : {}) as Promise<{ steady: SteadyWindow[] }>;
  }

  generateReport(req: ReportRequest): Promise<ReportResult> {
    return this.api.generate_report(req as unknown as Record<string, unknown>) as Promise<ReportResult>;
  }

  async defaultHtmlTemplate(): Promise<string> {
    const r = (await this.api.default_html_template()) as { template: string };
    return r.template;
  }

  saveFile(filename: string, dataB64: string): Promise<SaveResult> {
    return this.api.save_dialog({ filename, data_b64: dataB64 }) as Promise<SaveResult>;
  }

  pendingCrash(): Promise<PendingCrashStatus> {
    return this.api.pending_crash() as Promise<PendingCrashStatus>;
  }

  emailCrashReport(): Promise<CrashReportResult> {
    return this.api.email_crash_report({}) as Promise<CrashReportResult>;
  }

  async dismissCrashReport(): Promise<void> {
    await this.api.dismiss_crash_report();
  }
}
