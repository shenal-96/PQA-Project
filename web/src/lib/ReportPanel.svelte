<script lang="ts">
  import type { AnalysisBackend } from '../backend';
  import type { Caps, ReportFields, ReportRequest, ReportResult } from '../backend/types';

  let {
    backend,
    caps,
  }: {
    backend: AnalysisBackend | undefined;
    caps: Caps | undefined;
  } = $props();

  const FIELDS_KEY = 'pqa.report.v1';
  const DEFAULT_FIELDS: ReportFields = {
    report_title: '',
    pqa_serial: '',
    gen_sn: '',
    site_address: '',
    custom_text: '',
  };

  function loadFields(): ReportFields {
    try {
      const raw = localStorage.getItem(FIELDS_KEY);
      if (raw) return { ...DEFAULT_FIELDS, ...JSON.parse(raw) };
    } catch {
      /* ignore */
    }
    return { ...DEFAULT_FIELDS };
  }

  let fields = $state<ReportFields>(loadFields());
  let filename = $state('PQA_Report');
  let outPdf = $state(true);
  let outHtml = $state(false);
  let outDocx = $state(false);
  let docxTemplateB64 = $state<string | undefined>(undefined);
  let docxTemplateName = $state<string | undefined>(undefined);

  let busy = $state(false);
  let statusMsg = $state<string | undefined>(undefined);
  let statusOk = $state(true);
  let warnings = $state<string[]>([]);
  let log = $state<string | undefined>(undefined);
  let arts = $state<{ name: string; mime: string; b64: string }[]>([]);

  const canReport = $derived(caps?.canReport === true);
  const canSave = $derived(typeof backend?.saveFile === 'function');
  const nothingSelected = $derived(!outPdf && !outHtml && !outDocx);

  function persist() {
    try {
      localStorage.setItem(FIELDS_KEY, JSON.stringify(fields));
    } catch {
      /* ignore */
    }
  }

  function utf8ToB64(s: string): string {
    return btoa(unescape(encodeURIComponent(s)));
  }
  function b64ToBlob(b64: string, mime: string): Blob {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: mime });
  }

  async function onDocxTemplate(ev: Event) {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      docxTemplateB64 = undefined;
      docxTemplateName = undefined;
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const res = reader.result as string;
      docxTemplateB64 = res.slice(res.indexOf(',') + 1);
      docxTemplateName = file.name;
    };
    reader.readAsDataURL(file);
  }

  async function generate() {
    if (!backend || !canReport) return;
    busy = true;
    statusMsg = undefined;
    warnings = [];
    log = undefined;
    arts = [];
    persist();
    try {
      const req: ReportRequest = {
        fields,
        filename: filename || 'PQA_Report',
        outputs: { pdf: outPdf, html: outHtml, docx: outDocx },
        docx_template_b64: outDocx ? docxTemplateB64 : undefined,
      };
      const res: ReportResult = await backend.generateReport(req);
      warnings = res.warnings ?? [];
      log = res.log || undefined;
      const out: { name: string; mime: string; b64: string }[] = [];
      if (res.artifacts.pdf_b64) out.push({ name: `${res.filename}.pdf`, mime: 'application/pdf', b64: res.artifacts.pdf_b64 });
      if (res.artifacts.html) out.push({ name: `${res.filename}.html`, mime: 'text/html', b64: utf8ToB64(res.artifacts.html) });
      if (res.artifacts.docx_b64)
        out.push({ name: `${res.filename}.docx`, mime: res.artifacts.docx_mime ?? 'application/octet-stream', b64: res.artifacts.docx_b64 });
      arts = out;
      statusOk = out.length > 0;
      statusMsg = out.length ? `Generated ${out.length} file${out.length > 1 ? 's' : ''}.` : 'No files were generated — see warnings.';
    } catch (e) {
      statusOk = false;
      statusMsg = `Report failed: ${String(e)}`;
    } finally {
      busy = false;
    }
  }

  function download(a: { name: string; mime: string; b64: string }) {
    const url = URL.createObjectURL(b64ToBlob(a.b64, a.mime));
    const link = document.createElement('a');
    link.href = url;
    link.download = a.name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function saveAs(a: { name: string; mime: string; b64: string }) {
    if (!backend?.saveFile) {
      download(a);
      return;
    }
    try {
      const res = await backend.saveFile(a.name, a.b64);
      if (res.path) statusMsg = `Saved to ${res.path}`;
      else if (res.error) {
        // No native dialog available — fall back to a browser download.
        download(a);
      }
    } catch {
      download(a);
    }
  }
</script>

<div class="report">
  {#if !canReport}
    <div class="note">Report generation runs in the desktop app. The in-browser preview can't render report images or PDFs.</div>
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
    <span class="lbl">Outputs</span>
    <label class="chk"><input type="checkbox" bind:checked={outPdf} disabled={!canReport} /> PDF</label>
    <label class="chk"><input type="checkbox" bind:checked={outHtml} disabled={!canReport} /> HTML</label>
    <label class="chk"><input type="checkbox" bind:checked={outDocx} disabled={!canReport} /> Word (.docx)</label>
  </div>

  {#if outDocx}
    <div class="docx-tpl">
      <label class="file-btn" class:disabled={!canReport}>
        {docxTemplateName ? `Template: ${docxTemplateName}` : 'Choose Word template (.docx)…'}
        <input type="file" accept=".docx" onchange={onDocxTemplate} disabled={!canReport} hidden />
      </label>
      <span class="hint">Word output is injected into your template's {`{{placeholders}}`}.</span>
    </div>
  {/if}

  <button class="gen" onclick={generate} disabled={!canReport || busy || nothingSelected}>
    {busy ? 'Generating…' : '📄 Generate Report'}
  </button>
  {#if nothingSelected && canReport}<span class="hint">Select at least one output format.</span>{/if}

  {#if statusMsg}<div class="status" class:ok={statusOk} class:bad={!statusOk}>{statusMsg}</div>{/if}

  {#if arts.length}
    <div class="downloads">
      {#each arts as a}
        <div class="dl">
          <span class="fname">{a.name}</span>
          <button class="dl-btn" onclick={() => (canSave ? saveAs(a) : download(a))}>{canSave ? '💾 Save As…' : '⬇ Download'}</button>
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
</div>

<style>
  .report { display: flex; flex-direction: column; gap: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--card); padding: 16px; }
  .note { background: #eff6ff; color: #1d4ed8; padding: 8px 12px; border-radius: 8px; font-size: 13px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 16px; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-sub); }
  label.wide { grid-column: 1 / -1; }
  input[type='text'], textarea { border: 1px solid var(--border); border-radius: 7px; padding: 7px 9px; font-size: 13px; font-family: 'JetBrains Mono', monospace; color: var(--text-main); background: #fff; width: 100%; }
  input:disabled, textarea:disabled { background: #f1f5f9; color: #94a3b8; }
  textarea { resize: vertical; }
  .outputs { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; border-top: 1px solid var(--border); padding-top: 12px; }
  .outputs .lbl { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-sub); font-weight: 600; }
  .chk { flex-direction: row; align-items: center; gap: 6px; font-size: 13px; color: var(--text-main); }
  .docx-tpl { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .file-btn { flex-direction: row; align-items: center; background: #1e293b; color: #fff; padding: 8px 12px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .file-btn.disabled { background: #cbd5e1; cursor: not-allowed; }
  .hint { font-size: 11px; color: var(--text-sub); }
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
  .log summary { font-size: 12px; color: var(--text-sub); cursor: pointer; }
  @media (max-width: 720px) { .grid { grid-template-columns: 1fr; } }
</style>
