<script lang="ts">
  import { onMount } from 'svelte';
  import type { AnalysisBackend } from '../backend';
  import type { Caps, EventRecord, ReportFields, ReportRequest, ReportResult, SnapshotOpts, TemplateInfo } from '../backend/types';
  import type { DisplayOptions } from '../config/defaults';

  let {
    backend,
    caps,
    displayOpts,
    events = [],
    snapshotOpts,
  }: {
    backend: AnalysisBackend | undefined;
    caps: Caps | undefined;
    displayOpts?: DisplayOptions;
    events?: EventRecord[];
    /** Per-event snapshot window/time-shift tweaks (keyed by event index) so the
     *  report's clean snapshots match the on-screen ones the user tuned. */
    snapshotOpts?: Record<number, SnapshotOpts>;
  } = $props();

  const FIELDS_KEY = 'pqa.report.v1';
  const PREFS_KEY = 'pqa.report.prefs.v1';
  const DEFAULT_FIELDS: ReportFields = {
    report_title: '',
    pqa_serial: '',
    gen_sn: '',
    site_address: '',
    custom_text: '',
  };

  // Download-format presets (mirrors the Streamlit "Download Format" selector).
  // Each maps to the build_report `outputs` flags; Word formats require a template.
  type Fmt = 'PDF' | 'HTML' | 'HTML + PDF' | 'Word (.docx)' | 'Word + PDF';
  const FORMATS: Fmt[] = ['PDF', 'HTML', 'HTML + PDF', 'Word (.docx)', 'Word + PDF'];
  function outputsFor(fmt: Fmt) {
    return {
      pdf: fmt === 'PDF' || fmt === 'HTML + PDF' || fmt === 'Word + PDF',
      html: fmt === 'HTML' || fmt === 'HTML + PDF',
      docx: fmt === 'Word (.docx)' || fmt === 'Word + PDF',
    };
  }

  // The {{placeholders}} the report engine understands (report.get_placeholder_map).
  const PLACEHOLDERS = [
    '{{Report_Title}}', '{{PQID}}', '{{Gen_SN}}', '{{Site_Address}}', '{{Custom_Field}}',
    '{{Date}}', '{{Start Time}}', '{{End Time}}', '{{Compliance_Table}}',
    '{{Avg_Voltage_LL}}', '{{Avg_kW}}', '{{Avg_Current}}', '{{Avg_Frequency}}',
    '{{Avg_THD_F}}', '{{Avg_PF}}', '{{Snapshot_1}}', '{{Snapshot_2}}', '…',
  ];

  function loadFields(): ReportFields {
    try {
      const raw = localStorage.getItem(FIELDS_KEY);
      if (raw) return { ...DEFAULT_FIELDS, ...JSON.parse(raw) };
    } catch {
      /* ignore */
    }
    return { ...DEFAULT_FIELDS };
  }

  function loadPrefs(): { format: Fmt; template: string } {
    try {
      const raw = localStorage.getItem(PREFS_KEY);
      if (raw) {
        const p = JSON.parse(raw);
        return { format: FORMATS.includes(p.format) ? p.format : 'PDF', template: p.template ?? '' };
      }
    } catch {
      /* ignore */
    }
    return { format: 'PDF', template: '' };
  }

  let fields = $state<ReportFields>(loadFields());
  let filename = $state('PQA_Report');
  const _prefs = loadPrefs();
  let format = $state<Fmt>(_prefs.format);

  // Word template library (persisted host-side).
  let templates = $state<TemplateInfo[]>([]);
  let selectedTemplate = $state<string>(_prefs.template);
  let tplBusy = $state(false);
  let tplError = $state<string | undefined>(undefined);

  // Snapshot slots in the built-in HTML template (for the non-Word completeness check).
  let defaultSnapMax = $state(10);

  let busy = $state(false);
  let statusMsg = $state<string | undefined>(undefined);
  let statusOk = $state(true);
  let warnings = $state<string[]>([]);
  let log = $state<string | undefined>(undefined);
  let removeNrWarnings = $state(false);

  type Artifact = { name: string; mime: string; b64: string };
  let arts = $state<Artifact[]>([]);
  // Persistent list of reports generated this session (most recent first).
  let history = $state<{ name: string; when: string; arts: Artifact[] }[]>([]);

  const canReport = $derived(caps?.canReport === true);
  const canSave = $derived(typeof backend?.saveFile === 'function');
  const outputs = $derived(outputsFor(format));
  const needsTemplate = $derived(outputs.docx);
  const selectedTpl = $derived(templates.find((t) => t.name === selectedTemplate));

  const nEvents = $derived(events?.length ?? 0);
  const hasNotRecovered = $derived(
    events.some((e) => e['V_not_recovered'] === true || e['F_not_recovered'] === true),
  );

  // Pre-flight: which {{Snapshot_N}} placeholders the active template is missing
  // for the detected events. Word → the selected template's slots; otherwise the
  // built-in HTML template (Snapshot_1..defaultSnapMax).
  const missingSnapshots = $derived.by(() => {
    if (nEvents === 0) return [] as number[];
    if (needsTemplate) {
      if (!selectedTpl) return [];
      const have = new Set(selectedTpl.snapshot_indices);
      return Array.from({ length: nEvents }, (_, i) => i + 1).filter((n) => !have.has(n));
    }
    return Array.from({ length: nEvents }, (_, i) => i + 1).filter((n) => n > defaultSnapMax);
  });

  const blockedByNr = $derived(hasNotRecovered && !removeNrWarnings);
  const blockedByTpl = $derived(needsTemplate && !selectedTemplate);
  const canGenerate = $derived(canReport && !busy && !blockedByNr && !blockedByTpl);

  onMount(async () => {
    if (!canReport || !backend) return;
    try {
      if (backend.listTemplates) templates = await backend.listTemplates();
    } catch {
      /* a missing library is not an error — the user just hasn't uploaded one */
    }
    try {
      const tpl = await backend.defaultHtmlTemplate();
      const idxs = [...tpl.matchAll(/\{\{Snapshot_(\d+)\}\}/g)].map((m) => Number(m[1]));
      if (idxs.length) defaultSnapMax = Math.max(...idxs);
    } catch {
      /* keep the default of 10 */
    }
  });

  function persistFields() {
    try {
      localStorage.setItem(FIELDS_KEY, JSON.stringify(fields));
    } catch {
      /* ignore */
    }
  }
  function persistPrefs() {
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify({ format, template: selectedTemplate }));
    } catch {
      /* ignore */
    }
  }
  $effect(persistPrefs);

  function utf8ToB64(s: string): string {
    return btoa(unescape(encodeURIComponent(s)));
  }
  function b64ToBlob(b64: string, mime: string): Blob {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: mime });
  }
  function fmtSize(n: number): string {
    return n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
  }

  async function onTemplateUpload(ev: Event) {
    const input = ev.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    input.value = ''; // allow re-selecting the same file later
    if (!files.length || !backend?.saveTemplate) return;
    tplBusy = true;
    tplError = undefined;
    try {
      let latest = templates;
      for (const f of files) latest = await backend.saveTemplate(f);
      templates = latest;
      // Auto-select when exactly one was just uploaded (matches Streamlit).
      if (files.length === 1) selectedTemplate = templates.at(-1)?.name ?? selectedTemplate;
    } catch (e) {
      tplError = `Upload failed: ${String(e)}`;
    } finally {
      tplBusy = false;
    }
  }

  async function removeTemplate(name: string) {
    if (!backend?.deleteTemplate) return;
    tplBusy = true;
    tplError = undefined;
    try {
      templates = await backend.deleteTemplate(name);
      if (selectedTemplate === name) selectedTemplate = '';
    } catch (e) {
      tplError = `Remove failed: ${String(e)}`;
    } finally {
      tplBusy = false;
    }
  }

  async function generate() {
    if (!backend || !canGenerate) return;
    busy = true;
    statusMsg = undefined;
    warnings = [];
    log = undefined;
    arts = [];
    persistFields();
    try {
      // Carry the per-event snapshot window/time-shift tweaks into the report so
      // its clean snapshots match what the user tuned on screen (port of #21).
      const winOv: Record<number, number> = {};
      const offOv: Record<number, number> = {};
      for (const [k, o] of Object.entries(snapshotOpts ?? {})) {
        const i = Number(k);
        if (o?.window_s != null) winOv[i] = o.window_s;
        if (o?.time_offset_s) offOv[i] = o.time_offset_s; // skip the default 0 s
      }
      const req: ReportRequest = {
        fields,
        filename: filename || 'PQA_Report',
        outputs,
        docx_template_name: needsTemplate ? selectedTemplate : undefined,
        clear_not_recovered: hasNotRecovered && removeNrWarnings ? true : undefined,
        rated_load_kw: displayOpts?.rated_load_kw ?? null,
        image_options: displayOpts
          ? {
              show_limits: displayOpts.show_limits,
              show_tolerance_band: displayOpts.show_tolerance_band,
              show_deviation_limits: displayOpts.show_deviation_limits,
              show_intersections: displayOpts.show_intersections,
              show_max_deviation: displayOpts.show_max_deviation,
            }
          : undefined,
        snapshot_window_overrides: Object.keys(winOv).length ? winOv : undefined,
        snapshot_offset_overrides: Object.keys(offOv).length ? offOv : undefined,
      };
      const res: ReportResult = await backend.generateReport(req);
      warnings = res.warnings ?? [];
      log = res.log || undefined;
      const out: Artifact[] = [];
      if (res.artifacts.pdf_b64) out.push({ name: `${res.filename}.pdf`, mime: 'application/pdf', b64: res.artifacts.pdf_b64 });
      if (res.artifacts.html) out.push({ name: `${res.filename}.html`, mime: 'text/html', b64: utf8ToB64(res.artifacts.html) });
      if (res.artifacts.docx_b64)
        out.push({ name: `${res.filename}.docx`, mime: res.artifacts.docx_mime ?? 'application/octet-stream', b64: res.artifacts.docx_b64 });
      arts = out;
      statusOk = out.length > 0;
      statusMsg = out.length ? `Generated ${out.length} file${out.length > 1 ? 's' : ''}.` : 'No files were generated — see warnings.';
      if (out.length) {
        const when = new Date().toLocaleTimeString();
        history = [{ name: res.filename, when, arts: out }, ...history].slice(0, 10);
      }
    } catch (e) {
      statusOk = false;
      statusMsg = `Report failed: ${String(e)}`;
    } finally {
      busy = false;
    }
  }

  function download(a: Artifact) {
    const url = URL.createObjectURL(b64ToBlob(a.b64, a.mime));
    const link = document.createElement('a');
    link.href = url;
    link.download = a.name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function saveAs(a: Artifact) {
    if (!backend?.saveFile) {
      download(a);
      return;
    }
    try {
      const res = await backend.saveFile(a.name, a.b64);
      if (res.path) statusMsg = `Saved to ${res.path}`;
      else if (res.error) download(a);
    } catch {
      download(a);
    }
  }
  const grab = (a: Artifact) => (canSave ? saveAs(a) : download(a));
</script>

<div class="report">
  {#if !canReport}
    <div class="note">Report generation runs in the desktop app. The in-browser preview can't render report images, manage templates, or produce PDFs.</div>
  {/if}

  <div class="grid">
    <label>Report title<input type="text" bind:value={fields.report_title} placeholder="Client / site name" disabled={!canReport} /></label>
    <label>Filename<input type="text" bind:value={filename} placeholder="PQA_Report" disabled={!canReport} /></label>
    <label>PQA serial no.<input type="text" bind:value={fields.pqa_serial} placeholder="PQA-…" disabled={!canReport} /></label>
    <label>Generator S/N<input type="text" bind:value={fields.gen_sn} placeholder="Gen S/N" disabled={!canReport} /></label>
    <label class="wide">Site address<input type="text" bind:value={fields.site_address} placeholder="Site address" disabled={!canReport} /></label>
    <label class="wide">Notes<textarea bind:value={fields.custom_text} rows="2" placeholder="Custom notes for the report" disabled={!canReport}></textarea></label>
  </div>

  <div class="outputs">
    <label class="fmt">Download format
      <select bind:value={format} disabled={!canReport}>
        {#each FORMATS as f}<option value={f}>{f}</option>{/each}
      </select>
    </label>
    <span class="hint">PDF/HTML use the built-in report; Word injects your uploaded template.</span>
  </div>

  {#if needsTemplate}
    <div class="tpl">
      <div class="tpl-head">
        <label class="file-btn" class:disabled={!canReport || tplBusy}>
          {tplBusy ? 'Uploading…' : '＋ Upload Word template(s) (.docx)'}
          <input type="file" accept=".docx" multiple onchange={onTemplateUpload} disabled={!canReport || tplBusy} hidden />
        </label>
        <span class="hint">Saved on this PC — they persist across restarts.</span>
      </div>

      {#if tplError}<div class="status bad">{tplError}</div>{/if}

      {#if templates.length}
        <ul class="tpl-list">
          {#each templates as t}
            <li class:sel={t.name === selectedTemplate}>
              <button class="pick" onclick={() => (selectedTemplate = t.name)} title="Select this template">
                <span class="dot">{t.name === selectedTemplate ? '◉' : '○'}</span>
                <span class="tname">{t.name}</span>
                <span class="meta">{fmtSize(t.size)} · {t.snapshot_max} snapshot slot{t.snapshot_max === 1 ? '' : 's'}</span>
              </button>
              <button class="rm" onclick={() => removeTemplate(t.name)} title="Remove {t.name}" disabled={tplBusy}>✕</button>
            </li>
          {/each}
        </ul>
      {:else if canReport}
        <div class="hint empty-tpl">No templates yet — upload a .docx with {`{{placeholders}}`} to generate a Word report.</div>
      {/if}
    </div>
  {/if}

  <details class="ph">
    <summary>Available placeholders</summary>
    <div class="ph-body">
      <p>Use these tokens in your Word template (or the built-in HTML report):</p>
      <div class="chips">
        {#each PLACEHOLDERS as p}<code>{p}</code>{/each}
      </div>
      <p class="hint">One {`{{Snapshot_N}}`} per detected event (N = 1, 2, 3 …).</p>
    </div>
  </details>

  <!-- Pre-flight checks -->
  {#if needsTemplate && selectedTemplate && missingSnapshots.length}
    <div class="status bad">
      Selected template is missing {missingSnapshots.length} snapshot placeholder{missingSnapshots.length === 1 ? '' : 's'} for the
      {nEvents} detected event{nEvents === 1 ? '' : 's'}:
      {missingSnapshots.map((n) => `{{Snapshot_${n}}}`).join(', ')}
    </div>
  {:else if !needsTemplate && missingSnapshots.length}
    <div class="status bad">
      {nEvents} events detected but the built-in report has only {defaultSnapMax} snapshot slots — events
      {missingSnapshots.join(', ')} won't appear. Use a Word template with more {`{{Snapshot_N}}`} placeholders.
    </div>
  {/if}

  {#if hasNotRecovered}
    <div class="nr">
      <div class="nr-warn">⚠️ One or more events did not recover from the previous step. The report will show these flags unless removed.</div>
      <label class="chk"><input type="checkbox" bind:checked={removeNrWarnings} disabled={!canReport} /> Remove warnings from report</label>
    </div>
  {/if}

  <button class="gen" onclick={generate} disabled={!canGenerate}>
    {busy ? 'Generating…' : '📄 Generate Report'}
  </button>
  {#if blockedByTpl && canReport}<span class="hint">Upload and select a Word template to generate a {format}.</span>{/if}
  {#if blockedByNr}<span class="hint">Acknowledge the not-recovered warning above to enable generation.</span>{/if}

  {#if statusMsg}<div class="status" class:ok={statusOk} class:bad={!statusOk}>{statusMsg}</div>{/if}

  {#if arts.length}
    <div class="downloads">
      {#each arts as a}
        <div class="dl">
          <span class="fname">{a.name}</span>
          <button class="dl-btn" onclick={() => grab(a)}>{canSave ? '💾 Save As…' : '⬇ Download'}</button>
        </div>
      {/each}
    </div>
  {/if}

  {#if warnings.length}
    <ul class="warnings">
      {#each warnings as w}<li>{w}</li>{/each}
    </ul>
  {/if}

  {#if log}
    <details class="log"><summary>Report log</summary><pre>{log}</pre></details>
  {/if}

  {#if history.length}
    <details class="history" open>
      <summary>Generated reports ({history.length})</summary>
      <div class="hist-body">
        {#each history as h}
          <div class="hist-row">
            <span class="hist-name">{h.name}</span>
            <span class="hist-when">{h.when}</span>
            <span class="hist-arts">
              {#each h.arts as a}
                <button class="hist-dl" onclick={() => grab(a)} title={a.name}>{a.name.split('.').pop()?.toUpperCase()}</button>
              {/each}
            </span>
          </div>
        {/each}
      </div>
    </details>
  {/if}
</div>

<style>
  .report { display: flex; flex-direction: column; gap: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--card); padding: 16px; }
  .note { background: #eff6ff; color: #1d4ed8; padding: 8px 12px; border-radius: 8px; font-size: 13px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 16px; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-sub); }
  label.wide { grid-column: 1 / -1; }
  input[type='text'], textarea, select { border: 1px solid var(--border); border-radius: 7px; padding: 7px 9px; font-size: 13px; font-family: 'JetBrains Mono', monospace; color: var(--text-main); background: #fff; width: 100%; }
  input:disabled, textarea:disabled, select:disabled { background: #f1f5f9; color: #94a3b8; }
  textarea { resize: vertical; }
  .outputs { display: flex; align-items: flex-end; gap: 16px; flex-wrap: wrap; border-top: 1px solid var(--border); padding-top: 12px; }
  .fmt { max-width: 220px; }
  .fmt select { font-weight: 600; }
  .hint { font-size: 11px; color: var(--text-sub); }
  /* Template library */
  .tpl { display: flex; flex-direction: column; gap: 8px; background: #f8fafc; border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
  .tpl-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .file-btn { flex-direction: row; align-items: center; background: #1e293b; color: #fff; padding: 8px 12px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .file-btn.disabled { background: #cbd5e1; cursor: not-allowed; }
  .tpl-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .tpl-list li { display: flex; align-items: stretch; gap: 6px; }
  .tpl-list li.sel .pick { border-color: var(--blue); background: #eff6ff; }
  .pick { flex: 1; display: flex; align-items: center; gap: 8px; text-align: left; background: #fff; border: 1px solid var(--border); border-radius: 7px; padding: 7px 10px; cursor: pointer; font-size: 13px; color: var(--text-main); }
  .pick .dot { color: var(--blue); font-size: 13px; }
  .pick .tname { font-family: 'JetBrains Mono', monospace; font-weight: 600; }
  .pick .meta { margin-left: auto; font-size: 11px; color: var(--text-sub); }
  .rm { background: #fff; border: 1px solid var(--border); border-radius: 7px; width: 34px; cursor: pointer; color: #b91c1c; font-size: 13px; }
  .rm:hover { background: #fee2e2; }
  .rm:disabled { color: #cbd5e1; cursor: not-allowed; }
  .empty-tpl { padding: 4px 2px; }
  /* Placeholders reference */
  .ph summary { font-size: 12px; color: var(--text-sub); cursor: pointer; }
  .ph-body { padding: 8px 2px 2px; font-size: 12px; color: var(--text-sub); display: flex; flex-direction: column; gap: 6px; }
  .chips { display: flex; flex-wrap: wrap; gap: 5px; }
  .chips code { background: #0f172a; color: #cbd5e1; padding: 2px 7px; border-radius: 5px; font-size: 11px; }
  /* Not-recovered gate */
  .nr { display: flex; flex-direction: column; gap: 6px; background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 10px 12px; }
  .nr-warn { font-size: 12px; color: #b45309; }
  .chk { flex-direction: row; align-items: center; gap: 6px; font-size: 13px; color: var(--text-main); }
  .gen { align-self: flex-start; background: var(--blue); color: #fff; border: none; padding: 10px 18px; border-radius: 8px; font-weight: 700; cursor: pointer; }
  .gen:disabled { background: #cbd5e1; cursor: not-allowed; }
  .status { padding: 8px 12px; border-radius: 8px; font-size: 13px; }
  .status.ok { background: #dcfce7; color: #15803d; }
  .status.bad { background: #fee2e2; color: #b91c1c; }
  .downloads { display: flex; flex-direction: column; gap: 8px; }
  .dl { display: flex; align-items: center; gap: 12px; background: #f8fafc; border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; }
  .dl .fname { font-family: 'JetBrains Mono', monospace; font-size: 13px; flex: 1; }
  .dl-btn { background: var(--blue); color: #fff; border: none; border-radius: 7px; padding: 6px 12px; font-size: 12px; font-weight: 600; cursor: pointer; }
  .warnings { margin: 0; padding-left: 18px; color: #b45309; font-size: 12px; display: flex; flex-direction: column; gap: 4px; }
  .log pre { background: #0f172a; color: #cbd5e1; padding: 10px; border-radius: 8px; font-size: 11px; overflow-x: auto; white-space: pre-wrap; }
  .log summary, .history summary { font-size: 12px; color: var(--text-sub); cursor: pointer; }
  .history { border-top: 1px solid var(--border); padding-top: 10px; }
  .hist-body { display: flex; flex-direction: column; gap: 6px; padding-top: 8px; }
  .hist-row { display: flex; align-items: center; gap: 10px; font-size: 12px; }
  .hist-name { font-family: 'JetBrains Mono', monospace; font-weight: 600; color: var(--text-main); }
  .hist-when { color: var(--text-sub); }
  .hist-arts { margin-left: auto; display: flex; gap: 5px; }
  .hist-dl { background: #eff6ff; color: var(--blue); border: 1px solid #bfdbfe; border-radius: 6px; padding: 3px 9px; font-size: 11px; font-weight: 600; cursor: pointer; }
  @media (max-width: 720px) { .grid { grid-template-columns: 1fr; } }
</style>
