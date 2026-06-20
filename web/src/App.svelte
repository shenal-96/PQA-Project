<script lang="ts">
  import { onMount } from 'svelte';
  import { selectBackend } from './backend';
  import type { AnalysisBackend } from './backend';
  import type { AnalysisResult, Caps } from './backend/types';
  import { DEFAULT_CONFIG, loadConfig, saveConfig } from './config/defaults';
  import type { AnalysisConfigInput } from './config/defaults';
  import { metricLabel, METRIC_COLORS } from './lib/format';
  import Sidebar from './lib/Sidebar.svelte';
  import TimeSeriesChart from './lib/TimeSeriesChart.svelte';
  import ComplianceTable from './lib/ComplianceTable.svelte';

  let backend = $state<AnalysisBackend | undefined>(undefined);
  let caps = $state<Caps | undefined>(undefined);
  let result = $state<AnalysisResult | undefined>(undefined);
  let loading = $state(false);
  let error = $state<string | undefined>(undefined);
  let selected = $state('Avg_Voltage_LL');

  let config = $state<AnalysisConfigInput>({ ...DEFAULT_CONFIG });
  let activePreset = $state('None');
  let fileName = $state<string | undefined>(undefined);
  let loggerFormat = $state<string | null | undefined>(undefined);

  const metricKeys = $derived(result ? Object.keys(result.metrics) : []);
  const passCount = $derived(
    result ? result.events.filter((e) => String(e['Compliance_Status'] ?? '').toLowerCase() === 'pass').length : 0,
  );
  const failCount = $derived(result ? result.events.length - passCount : 0);
  const faultCount = $derived(result ? result.events.filter((e) => e['Potential_Fault'] === true).length : 0);

  async function run() {
    if (!backend) return;
    loading = true;
    error = undefined;
    try {
      const r = await backend.runAnalysis({ ...config });
      if (!r.metrics[selected]) selected = Object.keys(r.metrics)[0] ?? selected;
      result = r;
      saveConfig(config);
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
      fileName = meta.filename ?? file.name;
      loggerFormat = meta.logger_format;
      if (!meta.valid) {
        error = 'Invalid CSV: ' + meta.errors.join('; ');
        result = undefined;
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
    config = loadConfig();
    backend = await selectBackend();
    caps = await backend.caps();
    if (caps.platform === 'mock') {
      fileName = 'hioki_sample.csv (demo)';
      loggerFormat = 'hioki';
      await run(); // dev: render the bundled sample immediately
    }
  });
</script>

<div class="app">
  <Sidebar {config} {caps} {fileName} {loggerFormat} {loading} bind:activePreset onRun={run} {onFile} />

  <main class="main">
    {#if caps?.platform === 'mock'}
      <div class="banner info">Demo mode — the in-browser preview uses bundled sample data and ignores config changes. In the desktop app, Run Analysis recomputes from your CSV.</div>
    {/if}
    {#if error}<div class="banner error">{error}</div>{/if}

    {#if result}
      <section class="cards">
        <div class="card"><span class="k">Events</span><span class="v">{result.events.length}</span></div>
        <div class="card pass"><span class="k">Pass</span><span class="v">{passCount}</span></div>
        <div class="card fail"><span class="k">Fail</span><span class="v">{failCount}</span></div>
        <div class="card warn"><span class="k">Faults</span><span class="v">{faultCount}</span></div>
        <div class="card"><span class="k">Samples</span><span class="v">{result.n_rows}</span></div>
      </section>

      <div class="section-head"><span class="bar plots"></span><h2>Time-series</h2></div>
      <section class="tabs">
        {#each metricKeys as k}
          <button class="tab" class:active={k === selected} onclick={() => (selected = k)}>{metricLabel(k)}</button>
        {/each}
      </section>
      {#if result.metrics[selected]}
        <TimeSeriesChart series={result.metrics[selected]} label={metricLabel(selected)} color={METRIC_COLORS[selected] ?? '#2563eb'} />
      {/if}

      <div class="section-head"><span class="bar compliance"></span><h2>Compliance</h2></div>
      <ComplianceTable events={result.events} />
    {:else if loading}
      <div class="empty"><div class="bolt">⚡</div><p>Analyzing…</p></div>
    {:else}
      <div class="empty"><div class="bolt">⚡</div><p>Load a logger CSV and click <b>Run Analysis</b>.</p></div>
    {/if}
  </main>
</div>

<style>
  .app { display: flex; align-items: stretch; min-height: 100vh; }
  .main { flex: 1; min-width: 0; padding: clamp(1rem, 2.5vw, 2rem); display: flex; flex-direction: column; gap: 16px; }
  .banner { padding: 10px 14px; border-radius: 8px; font-size: 13px; }
  .banner.info { background: #eff6ff; color: #1d4ed8; }
  .banner.error { background: #fee2e2; color: #b91c1c; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }
  .card { background: var(--navy); border: 1px solid #1e293b; border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 6px; color: #e2e8f0; }
  .card .k { font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
  .card .v { font-size: 26px; font-weight: 700; }
  .card.pass { border-color: var(--green); } .card.pass .v { color: #4ade80; }
  .card.fail { border-color: var(--red); } .card.fail .v { color: #f87171; }
  .card.warn { border-color: var(--amber); } .card.warn .v { color: #fbbf24; }
  .section-head { display: flex; align-items: center; gap: 10px; margin-top: 6px; }
  .section-head .bar { width: 4px; height: 20px; border-radius: 2px; }
  .bar.plots { background: var(--cyan, #0891b2); } .bar.compliance { background: var(--blue); }
  h2 { margin: 0; font-size: 1.1rem; }
  .tabs { display: flex; flex-wrap: wrap; gap: 4px; border-bottom: 1px solid var(--border); }
  .tab { background: none; border: none; padding: 9px 14px; font-size: 14px; color: var(--text-sub); border-bottom: 2px solid transparent; margin-bottom: -1px; }
  .tab.active { color: var(--blue); border-bottom-color: var(--blue); font-weight: 600; }
  .empty { display: grid; place-items: center; gap: 10px; padding: 80px 0; color: var(--text-sub); border: 2px dashed var(--border); border-radius: 12px; }
  .empty .bolt { font-size: 34px; opacity: 0.4; }
  @media (max-width: 820px) { .app { flex-direction: column; } }
</style>
