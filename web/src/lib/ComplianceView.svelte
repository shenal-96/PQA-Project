<script lang="ts">
  import { onMount } from 'svelte';
  import type { AnalysisBackend } from '../backend';
  import type { AnalysisResult, Caps, CsvMeta, EventOverride, SnapshotData, SnapshotOpts } from '../backend/types';
  import { DEFAULT_CONFIG, loadConfig, saveConfig, resolveConfig, displayOptions } from '../config/defaults';
  import type { AnalysisConfigInput } from '../config/defaults';
  import type { SnapshotShow } from './SnapshotChart.svelte';
  import { metricLabel, METRIC_COLORS } from './format';
  import Sidebar from './Sidebar.svelte';
  import SidebarRedesign from './redesign/SidebarRedesign.svelte';
  import { themeState } from '../theme/theme.svelte';
  import TimeSeriesChart from './TimeSeriesChart.svelte';
  import DetectedEventsChart from './DetectedEventsChart.svelte';
  import ComplianceTable from './ComplianceTable.svelte';
  import ClipboardButtons from './ClipboardButtons.svelte';
  import EventCard from './EventCard.svelte';
  import ReportPanel from './ReportPanel.svelte';
  import IticChart from './IticChart.svelte';
  import SteadyStatePanel from './SteadyStatePanel.svelte';

  // mode = 'csv' (Compliance tab) or 'winscope' (WinScope tab). The only
  // difference is the file type + which backend loader runs; everything below
  // (analysis, charts, table, snapshots, recalc, reports) is shared.
  let { backend, caps, mode = 'csv' }: {
    backend: AnalysisBackend | undefined;
    caps: Caps | undefined;
    mode?: 'csv' | 'winscope';
  } = $props();

  const isWinscope = $derived(mode === 'winscope');
  const accept = $derived(isWinscope ? '.xls,.xlsx' : '.csv,text/csv');
  const fileLabel = $derived(isWinscope ? 'WinScope XLS' : 'Logger CSV');

  // Virtual first tab: the kW time-series with detected-event markers overlaid.
  const DETECTED = 'Detected_Events';

  let result = $state<AnalysisResult | undefined>(undefined);
  let loading = $state(false);
  let error = $state<string | undefined>(undefined);
  let selected = $state(DETECTED);

  let config = $state<AnalysisConfigInput>({ ...DEFAULT_CONFIG });
  let activePreset = $state('None');
  let fileName = $state<string | undefined>(undefined);
  let loggerFormat = $state<string | null | undefined>(undefined);

  // Time window (file-specific, not persisted with config). Empty = full file.
  let timeMin = $state<string | null>(null);
  let timeMax = $state<string | null>(null);
  let timeStart = $state('');
  let timeEnd = $state('');

  let snapshots = $state<(SnapshotData | null)[]>([]);
  let snapProgress = $state(0);
  let snapOpts = $state<Record<number, SnapshotOpts>>({});
  let overrides = $state<Record<number, EventOverride>>({});
  let recalcing = $state(false);

  const metricKeys = $derived(result ? Object.keys(result.metrics) : []);
  const passCount = $derived(
    result ? result.events.filter((e) => String(e['Compliance_Status'] ?? '').toLowerCase() === 'pass').length : 0,
  );
  const failCount = $derived(result ? result.events.length - passCount : 0);
  const faultCount = $derived(result ? result.events.filter((e) => e['Potential_Fault'] === true).length : 0);
  const anyOverride = $derived(
    Object.values(overrides).some(
      (o) =>
        (o.v_exit_offset ?? 0) !== 0 ||
        (o.f_exit_offset ?? 0) !== 0 ||
        o.v_rec_override != null ||
        o.f_rec_override != null,
    ),
  );
  const streaming = $derived(snapshots.length > 0 && snapshots.some((s) => s === null));
  const snapShow = $derived<SnapshotShow>({
    band: config.show_data_points && config.show_tolerance_band,
    limit: config.show_data_points && config.show_deviation_limits,
    intersections: config.show_data_points && config.show_intersections,
    extreme: config.show_data_points && config.show_max_deviation,
  });
  // δ band + dwell windows to overlay on the V/F time-series when steady-state
  // is enabled (only for the two metrics the δ bands apply to).
  const steadyBand = $derived.by(() => {
    if (!config.steady_state_enabled || !result?.steady) return undefined;
    if (selected === 'Avg_Voltage_LL') {
      const h = (config.nominal_voltage * config.steady_voltage_band_pct) / 100;
      return { lower: config.nominal_voltage - h, upper: config.nominal_voltage + h };
    }
    if (selected === 'Avg_Frequency') {
      const h = (config.nominal_frequency * config.steady_freq_band_pct) / 100;
      return { lower: config.nominal_frequency - h, upper: config.nominal_frequency + h };
    }
    return undefined;
  });
  const steadyWindows = $derived(
    steadyBand && result?.steady
      ? result.steady.map((w) => ({ start: String(w.Start_Timestamp), end: String(w.End_Timestamp) }))
      : undefined,
  );

  const stepsWarning = $derived(
    result && config.expected_steps != null && result.events.length !== config.expected_steps
      ? `Detected ${result.events.length} event(s) but ${config.expected_steps} were expected.`
      : undefined,
  );

  function loadFile(file: File): Promise<CsvMeta> {
    if (isWinscope) {
      if (!backend?.loadWinscope) throw new Error('WinScope loading is unavailable in this build.');
      return backend.loadWinscope(file);
    }
    return backend!.loadCsv(file);
  }

  async function run() {
    if (!backend) return;
    loading = true;
    error = undefined;
    overrides = {};
    snapOpts = {};
    snapshots = [];
    try {
      const r = await backend.runAnalysis({
        ...resolveConfig(config),
        time_start: timeStart || null,
        time_end: timeEnd || null,
      });
      if (selected !== DETECTED && !r.metrics[selected]) {
        selected = Object.keys(r.metrics)[0] ?? selected;
      }
      result = r;
      saveConfig(config);
      void streamSnapshots();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  async function streamSnapshots() {
    if (!backend || !result) return;
    const n = result.events.length;
    snapshots = new Array(n).fill(null);
    snapProgress = 0;
    for (let i = 0; i < n; i++) {
      try {
        snapshots[i] = await backend.snapshot(i, snapOpts[i] ?? {});
      } catch (e) {
        console.error('snapshot', i, e);
      }
      snapProgress = Math.round(((i + 1) / n) * 100);
    }
  }

  async function applySnapshot(i: number, opts: SnapshotOpts) {
    if (!backend) return;
    snapOpts[i] = opts;
    snapshots[i] = null;
    try {
      snapshots[i] = await backend.snapshot(i, opts);
    } catch (e) {
      console.error('snapshot apply', i, e);
    }
  }

  function onOverride(i: number, ov: EventOverride) {
    overrides = { ...overrides, [i]: ov };
  }

  async function recalc() {
    if (!backend || !result) return;
    recalcing = true;
    try {
      const r = await backend.recalc(overrides);
      result = { ...result, events: r.events, itic: r.itic ?? result.itic };
      await streamSnapshots();
    } catch (e) {
      error = String(e);
    } finally {
      recalcing = false;
    }
  }

  async function onFile(ev: Event) {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !backend) return;
    loading = true;
    error = undefined;
    try {
      const meta = await loadFile(file);
      fileName = meta.filename ?? file.name;
      loggerFormat = meta.logger_format;
      // Seed the time-window picker from the file's range; default to the full file.
      timeMin = meta.time_min ?? null;
      timeMax = meta.time_max ?? null;
      timeStart = '';
      timeEnd = '';
      if (!meta.valid) {
        error = 'Invalid file: ' + meta.errors.join('; ');
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
    if (caps?.platform === 'mock') {
      fileName = isWinscope ? 'winscope_sample.xls (demo)' : 'hioki_sample.csv (demo)';
      loggerFormat = isWinscope ? 'winscope' : 'hioki';
      try {
        // Pull the sample's time range so the demo shows the time-window slider.
        const meta = await loadFile(new File([], 'demo'));
        timeMin = meta.time_min ?? null;
        timeMax = meta.time_max ?? null;
      } catch {
        /* ignore — demo still runs without the slider */
      }
      void run(); // dev: render the bundled sample immediately
    }
  });
</script>

<div class="app">
  {#if themeState.current === 'redesign'}
    <SidebarRedesign {config} {caps} {backend} {fileName} {loggerFormat} {loading} {accept} {fileLabel}
      {timeMin} {timeMax} bind:timeStart bind:timeEnd
      bind:activePreset onRun={run} {onFile} />
  {:else}
    <Sidebar {config} {caps} {backend} {fileName} {loggerFormat} {loading} {accept} {fileLabel}
      {timeMin} {timeMax} bind:timeStart bind:timeEnd
      bind:activePreset onRun={run} {onFile} />
  {/if}

  <main class="main">
    {#if caps?.platform === 'mock'}
      <div class="banner info">Demo mode — the in-browser preview uses bundled sample data and ignores config changes. In the desktop app, Run Analysis recomputes from your file.</div>
    {/if}
    {#if error}<div class="banner error">{error}</div>{/if}
    {#if stepsWarning}<div class="banner warn">⚠ {stepsWarning}</div>{/if}

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
        <button class="tab" class:active={selected === DETECTED} onclick={() => (selected = DETECTED)}>Detected Events</button>
        {#each metricKeys as k}
          <button class="tab" class:active={k === selected} onclick={() => (selected = k)}>{metricLabel(k)}</button>
        {/each}
      </section>
      {#if selected === DETECTED}
        <DetectedEventsChart series={result.metrics['Avg_kW']} overlay={result.events_overlay ?? []} />
      {:else if result.metrics[selected]}
        <TimeSeriesChart series={result.metrics[selected]} label={metricLabel(selected)} color={METRIC_COLORS[selected] ?? '#2563eb'} band={steadyBand} windows={steadyWindows} />
      {/if}

      {#if result.itic}
        <div class="section-head"><span class="bar itic"></span><h2>ITIC (CBEMA) Curve</h2></div>
        <IticChart itic={result.itic} />
      {/if}

      <div class="section-head"><span class="bar compliance"></span><h2>Compliance</h2></div>
      <ComplianceTable events={result.events} />
      {#if result.events.length}<ClipboardButtons events={result.events} />{/if}

      {#if config.steady_state_enabled && result.steady}
        <div class="section-head">
          <span class="bar steady"></span><h2>Steady-state (ISO 8528-5 δ bands)</h2>
        </div>
        <SteadyStatePanel windows={result.steady} summary={result.steady_summary} {backend} {caps} />
      {/if}

      {#if result.events.length}
        <div class="section-head">
          <span class="bar snapshots"></span><h2>Event snapshots</h2>
          {#if streaming}<span class="muted">rendering {snapProgress}%</span>{/if}
        </div>
        {#if streaming}
          <div class="progress"><div class="bar-fill" style="width:{snapProgress}%"></div></div>
        {/if}
        <div class="events">
          {#each result.events as ev, i}
            <EventCard event={ev} index={i} snap={snapshots[i] ?? null} show={snapShow} onApply={applySnapshot} {onOverride} />
          {/each}
        </div>
        <div class="recalc-row">
          <button class="recalc" onclick={recalc} disabled={!anyOverride || recalcing}>
            {recalcing ? 'Recalculating…' : '🔄 Recalculate Compliance'}
          </button>
          {#if caps?.platform === 'mock'}
            <span class="muted">Recalculate runs in the desktop app (the in-browser preview can't recompute).</span>
          {/if}
        </div>
      {/if}

      <div class="section-head"><span class="bar reports"></span><h2>Report</h2></div>
      <ReportPanel {backend} {caps} displayOpts={displayOptions(config)} events={result.events} snapshotOpts={snapOpts} />
    {:else if loading}
      <div class="empty"><div class="bolt">⚡</div><p>Analyzing…</p></div>
    {:else}
      <div class="empty"><div class="bolt">⚡</div><p>Load a {isWinscope ? 'WinScope .xls' : 'logger CSV'} and click <b>Run Analysis</b>.</p></div>
    {/if}
  </main>
</div>

<style>
  .app { display: flex; align-items: stretch; height: 100%; overflow: hidden; }
  .main { flex: 1; min-width: 0; height: 100%; overflow-y: auto; padding: clamp(1rem, 2.5vw, 2rem); display: flex; flex-direction: column; gap: 16px; }
  /* In a fixed-height scroll column, keep children at intrinsic height (charts/
     table must not be compressed by flex-shrink — they overflow and scroll). */
  .main > :global(*) { flex-shrink: 0; }
  .banner { padding: 10px 14px; border-radius: 8px; font-size: 13px; }
  .banner.info { background: #eff6ff; color: #1d4ed8; }
  .banner.error { background: #fee2e2; color: #b91c1c; }
  .banner.warn { background: #fffbeb; color: #b45309; }
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
  .bar.steady { background: #0d9488; }
  h2 { margin: 0; font-size: 1.1rem; }
  .tabs { display: flex; flex-wrap: wrap; gap: 4px; border-bottom: 1px solid var(--border); }
  .tab { background: none; border: none; padding: 9px 14px; font-size: 14px; color: var(--text-sub); border-bottom: 2px solid transparent; margin-bottom: -1px; }
  .tab.active { color: var(--blue); border-bottom-color: var(--blue); font-weight: 600; }
  .empty { display: grid; place-items: center; gap: 10px; padding: 80px 0; color: var(--text-sub); border: 2px dashed var(--border); border-radius: 12px; }
  .empty .bolt { font-size: 34px; opacity: 0.4; }
  .bar.snapshots { background: #9333ea; }
  .bar.itic { background: var(--red, #dc2626); }
  .bar.reports { background: var(--green, #16a34a); }
  .muted { color: var(--text-sub); font-size: 12px; }
  .progress { height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden; }
  .progress .bar-fill { height: 100%; background: #9333ea; transition: width 0.2s; }
  .events { display: flex; flex-direction: column; gap: 10px; }
  .recalc-row { display: flex; align-items: center; gap: 12px; margin-top: 6px; flex-wrap: wrap; }
  .recalc { background: var(--blue); color: #fff; border: none; padding: 10px 18px; border-radius: 8px; font-weight: 700; cursor: pointer; }
  .recalc:disabled { background: #cbd5e1; cursor: not-allowed; }
  /* Narrow windows: stack and let the whole view scroll as one column. */
  @media (max-width: 820px) {
    .app { flex-direction: column; height: auto; overflow-y: auto; }
    .main { height: auto; overflow: visible; }
  }
</style>
