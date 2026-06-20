<script lang="ts">
  import type { AnalysisBackend } from '../backend';
  import type { Caps, EcuRecording } from '../backend/types';
  import EcuChart from './EcuChart.svelte';
  import type { EcuSeries } from './EcuChart.svelte';

  let { backend, caps }: { backend: AnalysisBackend | undefined; caps: Caps | undefined } = $props();

  const CUSTOM = '🎯 Custom Plot';

  let data = $state<EcuRecording | undefined>(undefined);
  let busy = $state(false);
  let error = $state<string | undefined>(undefined);
  let activeTab = $state<string>('');
  // Selected channel names per tab (group name or CUSTOM).
  let selectedByTab = $state<Record<string, string[]>>({});

  const canXls = $derived(caps?.canXls === true);
  const tabs = $derived(data ? [...Object.keys(data.groups), CUSTOM] : []);
  const channelsForTab = $derived(
    !data ? [] : activeTab === CUSTOM ? Object.keys(data.channels) : (data.groups[activeTab] ?? []),
  );
  const selected = $derived(selectedByTab[activeTab] ?? []);
  const series = $derived<EcuSeries[]>(
    !data ? [] : selected.map((name) => ({ name, label: data!.labels[name] ?? name, values: data!.channels[name] })),
  );

  function label(name: string): string {
    return data?.labels[name] ?? name;
  }

  function toggle(name: string) {
    const cur = new Set(selectedByTab[activeTab] ?? []);
    if (cur.has(name)) cur.delete(name);
    else cur.add(name);
    // Preserve channel order as listed for the tab.
    const ordered = channelsForTab.filter((c) => cur.has(c));
    selectedByTab = { ...selectedByTab, [activeTab]: ordered };
  }

  async function onFile(ev: Event) {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    if (!backend?.ecuRecording) {
      error = 'ECU plotting runs in the desktop app.';
      return;
    }
    busy = true;
    error = undefined;
    data = undefined;
    try {
      const rec = await backend.ecuRecording(file);
      data = rec;
      // Default each group tab to all its channels; custom plot starts empty.
      const init: Record<string, string[]> = {};
      for (const [g, cols] of Object.entries(rec.groups)) init[g] = [...cols];
      init[CUSTOM] = [];
      selectedByTab = init;
      activeTab = Object.keys(rec.groups)[0] ?? CUSTOM;
    } catch (e) {
      error = String(e);
    } finally {
      busy = false;
      input.value = '';
    }
  }
</script>

<main class="wrap">
  <div class="head">
    <span class="bar"></span>
    <h2>ECU Plotting</h2>
    <span class="sub">Time-series viewer for ECU recordings</span>
    <label class="file-btn" class:disabled={!canXls}>
      {data ? 'Change recording' : 'Load recording (.xls/.xlsx)'}
      <input type="file" accept=".xls,.xlsx" onchange={onFile} disabled={!canXls} hidden />
    </label>
  </div>

  {#if caps?.platform === 'mock'}
    <div class="banner info">Demo mode — showing a bundled sample recording. In the desktop app this loads your uploaded file.</div>
  {/if}
  {#if error}<div class="banner error">{error}</div>{/if}

  {#if busy}
    <div class="empty"><div class="bolt">🔌</div><p>Reading recording…</p></div>
  {:else if data}
    <div class="meta">
      <span class="fname">{data.filename}</span>
      <span>{data.n_rows} samples · {Object.keys(data.channels).length} channels</span>
    </div>

    <div class="grouptabs">
      {#each tabs as t}
        <button class="gtab" class:active={t === activeTab} onclick={() => (activeTab = t)}>
          {t}{#if t !== CUSTOM}<span class="count">{data.groups[t].length}</span>{/if}
        </button>
      {/each}
    </div>

    <div class="chips">
      {#each channelsForTab as name}
        <button class="chip" class:on={selected.includes(name)} onclick={() => toggle(name)} title={name}>
          {label(name)}
        </button>
      {/each}
      {#if channelsForTab.length === 0}<span class="muted">No channels in this group.</span>{/if}
    </div>

    {#if series.length}
      <EcuChart timestamps={data.timestamps} {series} />
    {:else}
      <div class="empty"><p>Select one or more channels above to plot.</p></div>
    {/if}
  {:else}
    <div class="empty"><div class="bolt">🔌</div><p>Load an ECU recording (.xls/.xlsx) to plot its channels, auto-grouped by type.</p></div>
  {/if}
</main>

<style>
  .wrap { padding: clamp(1rem, 2.5vw, 2rem); display: flex; flex-direction: column; gap: 16px; }
  .head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .head .bar { width: 4px; height: 22px; border-radius: 2px; background: var(--cyan, #0891b2); }
  h2 { margin: 0; font-size: 1.2rem; }
  .sub { color: var(--text-sub); font-size: 13px; }
  .head .file-btn { margin-left: auto; }
  .file-btn { background: #1e293b; color: #fff; padding: 9px 14px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .file-btn.disabled { background: #cbd5e1; cursor: not-allowed; }
  .banner { padding: 10px 14px; border-radius: 8px; font-size: 13px; }
  .banner.info { background: #eff6ff; color: #1d4ed8; }
  .banner.error { background: #fee2e2; color: #b91c1c; }
  .meta { display: flex; gap: 16px; align-items: center; font-size: 13px; color: var(--text-sub); }
  .meta .fname { font-family: 'JetBrains Mono', monospace; color: var(--text-main); font-weight: 600; }
  .grouptabs { display: flex; flex-wrap: wrap; gap: 4px; border-bottom: 1px solid var(--border); }
  .gtab { background: none; border: none; padding: 9px 14px; font-size: 14px; color: var(--text-sub); border-bottom: 2px solid transparent; margin-bottom: -1px; display: inline-flex; align-items: center; gap: 6px; }
  .gtab.active { color: var(--cyan, #0891b2); border-bottom-color: var(--cyan, #0891b2); font-weight: 600; }
  .gtab .count { background: #e2e8f0; color: #475569; border-radius: 999px; font-size: 11px; padding: 0 6px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { background: #fff; border: 1px solid var(--border); color: var(--text-sub); border-radius: 999px; padding: 5px 12px; font-size: 12px; }
  .chip.on { background: var(--cyan, #0891b2); border-color: var(--cyan, #0891b2); color: #fff; font-weight: 600; }
  .muted { color: var(--text-sub); font-size: 13px; }
  .empty { display: grid; place-items: center; gap: 10px; padding: 60px 0; color: var(--text-sub); border: 2px dashed var(--border); border-radius: 12px; }
  .empty .bolt { font-size: 30px; opacity: 0.4; }
</style>
