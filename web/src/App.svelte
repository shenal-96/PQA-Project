<script lang="ts">
  import { onMount } from 'svelte';
  import { selectBackend } from './backend';
  import type { AnalysisBackend } from './backend';
  import type { AnalysisResult, Caps } from './backend/types';
  import { metricLabel, METRIC_COLORS } from './lib/format';
  import TimeSeriesChart from './lib/TimeSeriesChart.svelte';
  import ComplianceTable from './lib/ComplianceTable.svelte';

  let backend = $state<AnalysisBackend | undefined>(undefined);
  let caps = $state<Caps | undefined>(undefined);
  let result = $state<AnalysisResult | undefined>(undefined);
  let loading = $state(false);
  let error = $state<string | undefined>(undefined);
  let selected = $state('Avg_Voltage_LL');

  const metricKeys = $derived(result ? Object.keys(result.metrics) : []);
  const passCount = $derived(
    result ? result.events.filter((e) => String(e['Compliance_Status'] ?? '').toLowerCase() === 'pass').length : 0,
  );
  const failCount = $derived(result ? result.events.length - passCount : 0);

  async function run() {
    if (!backend) return;
    loading = true;
    error = undefined;
    try {
      const r = await backend.runAnalysis({});
      if (!r.metrics[selected]) selected = Object.keys(r.metrics)[0] ?? selected;
      result = r;
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  async function onFile(ev: Event) {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !backend) return;
    loading = true;
    error = undefined;
    try {
      const meta = await backend.loadCsv(file);
      if (!meta.valid) {
        error = 'Invalid CSV: ' + meta.errors.join('; ');
        return;
      }
      await run();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
      input.value = '';
    }
  }

  onMount(async () => {
    backend = await selectBackend();
    caps = await backend.caps();
    if (caps.platform === 'mock') await run(); // dev: show the sample immediately
  });
</script>

<main>
  <header>
    <div class="brand">
      <div class="bolt">⚡</div>
      <div>
        <h1>PQA — Power Quality Analysis</h1>
        <p>ISO 8528 compliance · desktop</p>
      </div>
    </div>
    <div class="actions">
      {#if caps}
        <span class="env mono">{caps.platform}</span>
      {/if}
      <label class="btn">
        Load CSV
        <input type="file" accept=".csv,text/csv" onchange={onFile} hidden />
      </label>
    </div>
  </header>

  {#if error}
    <div class="banner error">{error}</div>
  {/if}
  {#if loading}
    <div class="banner muted">Working…</div>
  {/if}

  {#if result}
    <section class="cards">
      <div class="card"><span class="k">Events</span><span class="v">{result.events.length}</span></div>
      <div class="card pass"><span class="k">Pass</span><span class="v">{passCount}</span></div>
      <div class="card fail"><span class="k">Fail</span><span class="v">{failCount}</span></div>
      <div class="card"><span class="k">Samples</span><span class="v">{result.n_rows}</span></div>
      <div class="card"><span class="k">Logger</span><span class="v small">{result.logger_format ?? '—'}</span></div>
    </section>

    <section class="tabs">
      {#each metricKeys as k}
        <button class="tab" class:active={k === selected} onclick={() => (selected = k)}>
          {metricLabel(k)}
        </button>
      {/each}
    </section>

    {#if result.metrics[selected]}
      <TimeSeriesChart
        series={result.metrics[selected]}
        label={metricLabel(selected)}
        color={METRIC_COLORS[selected] ?? '#2563eb'}
      />
    {/if}

    <h2>Compliance</h2>
    <ComplianceTable events={result.events} />
  {:else if !loading}
    <div class="empty">
      <div class="bolt big">⚡</div>
      <p>Load a logger CSV to run the compliance analysis.</p>
    </div>
  {/if}
</main>

<style>
  main {
    max-width: 100%;
    padding: clamp(1rem, 3vw, 2.5rem);
    display: flex;
    flex-direction: column;
    gap: 18px;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }
  .brand { display: flex; align-items: center; gap: 14px; }
  .bolt {
    width: 42px; height: 42px;
    display: grid; place-items: center;
    background: var(--navy); color: #fff;
    border-radius: 10px; font-size: 20px;
  }
  .bolt.big { width: 64px; height: 64px; font-size: 30px; opacity: 0.5; }
  h1 { margin: 0; font-size: clamp(1.1rem, 2.2vw, 1.5rem); }
  header p { margin: 2px 0 0; color: var(--text-sub); font-size: 13px; }
  .actions { display: flex; align-items: center; gap: 10px; }
  .env {
    background: #e2e8f0; color: #334155;
    padding: 3px 10px; border-radius: 999px; font-size: 12px;
  }
  .btn {
    background: var(--blue); color: #fff;
    padding: 9px 16px; border-radius: 8px;
    font-weight: 600; font-size: 14px; cursor: pointer;
  }
  .banner { padding: 10px 14px; border-radius: 8px; font-size: 14px; }
  .banner.error { background: #fee2e2; color: #b91c1c; }
  .banner.muted { background: #eff6ff; color: #1d4ed8; }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
  }
  .card {
    background: var(--navy);
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 14px 16px;
    display: flex; flex-direction: column; gap: 6px;
    color: #e2e8f0;
  }
  .card .k { font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
  .card .v { font-size: 26px; font-weight: 700; }
  .card .v.small { font-size: 18px; }
  .card.pass { border-color: var(--green); }
  .card.pass .v { color: #4ade80; }
  .card.fail { border-color: var(--red); }
  .card.fail .v { color: #f87171; }
  .tabs { display: flex; flex-wrap: wrap; gap: 4px; border-bottom: 1px solid var(--border); }
  .tab {
    background: none; border: none;
    padding: 10px 14px; font-size: 14px; color: var(--text-sub);
    border-bottom: 2px solid transparent; margin-bottom: -1px;
  }
  .tab.active { color: var(--blue); border-bottom-color: var(--blue); font-weight: 600; }
  h2 { margin: 8px 0 0; font-size: 1.1rem; }
  .empty {
    display: grid; place-items: center; gap: 10px;
    padding: 80px 0; color: var(--text-sub);
    border: 2px dashed var(--border); border-radius: 12px;
  }
</style>
