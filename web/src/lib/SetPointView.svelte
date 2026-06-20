<script lang="ts">
  import type { AnalysisBackend } from '../backend';
  import type { Caps, SetpointResult } from '../backend/types';

  let { backend, caps }: { backend: AnalysisBackend | undefined; caps: Caps | undefined } = $props();

  let kind = $state<'xls' | 'csv'>('xls');
  let files = $state<File[]>([]);
  let busy = $state(false);
  let error = $state<string | undefined>(undefined);
  let result = $state<SetpointResult | undefined>(undefined);
  let filter = $state('');

  const canXls = $derived(caps?.canXls === true);
  const accept = $derived(kind === 'csv' ? '.csv' : '.xls,.xlsx');

  const fixedCols = $derived(result ? result.columns.slice(0, result.columns.length - result.labels.length) : []);
  const rows = $derived(
    result
      ? result.rows.filter((r) => {
          if (!filter.trim()) return true;
          const q = filter.toLowerCase();
          return result!.columns.some((c) => String(r[c] ?? '').toLowerCase().includes(q));
        })
      : [],
  );

  function onFiles(ev: Event) {
    const input = ev.target as HTMLInputElement;
    files = input.files ? Array.from(input.files) : [];
    result = undefined;
    error = undefined;
  }

  async function compare() {
    if (!backend?.compareSetpoint) {
      error = 'Set Point comparison runs in the desktop app.';
      return;
    }
    if (files.length < 2) {
      error = 'Select at least two files to compare.';
      return;
    }
    busy = true;
    error = undefined;
    result = undefined;
    try {
      result = await backend.compareSetpoint(kind, files);
    } catch (e) {
      error = String(e);
    } finally {
      busy = false;
    }
  }

  function downloadCsv() {
    if (!result) return;
    const esc = (v: unknown) => {
      const s = String(v ?? '');
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const lines = [result.columns.map(esc).join(',')];
    for (const r of rows) lines.push(result.columns.map((c) => esc(r[c])).join(','));
    const url = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'setpoint_differences.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
</script>

<main class="wrap">
  <div class="head">
    <span class="bar"></span>
    <h2>Set Point Comparison</h2>
    <span class="sub">Diff ECU parameter files across units</span>
  </div>

  {#if caps?.platform === 'mock'}
    <div class="banner info">Demo mode — showing a bundled sample diff. In the desktop app this compares your uploaded files.</div>
  {/if}

  <div class="controls">
    <div class="seg">
      <button class:on={kind === 'xls'} onclick={() => (kind = 'xls')}>XLS / XLSX</button>
      <button class:on={kind === 'csv'} onclick={() => (kind = 'csv')}>ComAp CSV</button>
    </div>
    <label class="file-btn" class:disabled={!canXls}>
      {files.length ? `${files.length} file${files.length > 1 ? 's' : ''} selected` : 'Choose files…'}
      <input type="file" {accept} multiple onchange={onFiles} disabled={!canXls} hidden />
    </label>
    <button class="go" onclick={compare} disabled={!canXls || busy || files.length < 2}>
      {busy ? 'Comparing…' : 'Compare'}
    </button>
  </div>

  {#if files.length}
    <div class="filelist">{files.map((f) => f.name).join('  ·  ')}</div>
  {/if}

  {#if error}<div class="banner error">{error}</div>{/if}

  {#if result}
    <div class="summary">
      <span><b>{result.n_files}</b> files</span>
      <span><b>{result.n_diffs}</b> differing locations</span>
      <input class="filter" type="text" bind:value={filter} placeholder="Filter rows…" />
      <button class="dl" onclick={downloadCsv} disabled={!rows.length}>⬇ Download CSV</button>
    </div>

    {#if result.n_diffs === 0}
      <div class="empty good">✓ No differences found across the selected files.</div>
    {:else}
      <div class="tablewrap">
        <table>
          <thead>
            <tr>
              {#each fixedCols as c}<th>{c}</th>{/each}
              {#each result.labels as l}<th class="filecol">{l}</th>{/each}
            </tr>
          </thead>
          <tbody>
            {#each rows as r}
              <tr>
                {#each fixedCols as c}<td>{r[c] ?? '—'}</td>{/each}
                {#each result.labels as l}<td class="num">{r[l] ?? '—'}</td>{/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      {#if rows.length === 0}<div class="empty">No rows match “{filter}”.</div>{/if}
    {/if}
  {:else if !busy}
    <div class="empty"><div class="bolt">🔧</div><p>Select two or more {kind === 'csv' ? 'ComAp CSV' : 'XLS/XLSX'} files and click <b>Compare</b>.</p></div>
  {/if}
</main>

<style>
  .wrap { height: 100%; overflow-y: auto; padding: clamp(1rem, 2.5vw, 2rem); display: flex; flex-direction: column; gap: 16px; }
  .wrap > :global(*) { flex-shrink: 0; }
  .head { display: flex; align-items: center; gap: 10px; }
  .head .bar { width: 4px; height: 22px; border-radius: 2px; background: var(--amber); }
  h2 { margin: 0; font-size: 1.2rem; }
  .sub { color: var(--text-sub); font-size: 13px; }
  .banner { padding: 10px 14px; border-radius: 8px; font-size: 13px; }
  .banner.info { background: #eff6ff; color: #1d4ed8; }
  .banner.error { background: #fee2e2; color: #b91c1c; }
  .controls { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .seg { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  .seg button { background: #fff; border: none; padding: 8px 14px; font-size: 13px; color: var(--text-sub); }
  .seg button.on { background: var(--blue); color: #fff; font-weight: 600; }
  .file-btn { background: #1e293b; color: #fff; padding: 9px 14px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .file-btn.disabled { background: #cbd5e1; cursor: not-allowed; }
  .go, .dl { background: var(--blue); color: #fff; border: none; padding: 9px 16px; border-radius: 8px; font-weight: 700; font-size: 13px; }
  .go:disabled, .dl:disabled { background: #cbd5e1; cursor: not-allowed; }
  .filelist { font-size: 12px; color: var(--text-sub); font-family: 'JetBrains Mono', monospace; }
  .summary { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; font-size: 13px; color: var(--text-sub); }
  .filter { margin-left: auto; border: 1px solid var(--border); border-radius: 7px; padding: 7px 10px; font-size: 13px; min-width: 200px; }
  .tablewrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; background: var(--card); }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }
  th { background: #f1f5f9; color: var(--text-sub); font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; position: sticky; top: 0; }
  th.filecol { color: var(--blue); }
  td.num { font-family: 'JetBrains Mono', monospace; }
  tbody tr:hover { background: #f8fafc; }
  .empty { display: grid; place-items: center; gap: 10px; padding: 60px 0; color: var(--text-sub); border: 2px dashed var(--border); border-radius: 12px; }
  .empty.good { color: #15803d; border-color: #bbf7d0; background: #f0fdf4; padding: 24px; }
  .empty .bolt { font-size: 30px; opacity: 0.4; }
</style>
