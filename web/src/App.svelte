<script lang="ts">
  import { onMount } from 'svelte';
  import { selectBackend } from './backend';
  import type { AnalysisBackend } from './backend';
  import type { Caps } from './backend/types';
  import ComplianceView from './lib/ComplianceView.svelte';
  import SetPointView from './lib/SetPointView.svelte';
  import EcuPlotView from './lib/EcuPlotView.svelte';

  let backend = $state<AnalysisBackend | undefined>(undefined);
  let caps = $state<Caps | undefined>(undefined);
  let ready = $state(false);

  type TabKey = 'compliance' | 'winscope' | 'setpoint' | 'ecu';
  const TABS: { key: TabKey; label: string; xls: boolean }[] = [
    { key: 'compliance', label: '⚡ Compliance', xls: false },
    { key: 'winscope', label: '📊 WinScope', xls: true },
    { key: 'setpoint', label: '🔧 Set Point', xls: true },
    { key: 'ecu', label: '🔌 ECU Plotting', xls: true },
  ];

  let tab = $state<TabKey>('compliance');
  // Lazy-mount each view on first visit, then keep it mounted (hidden) so its
  // state (loaded file, analysis, plots) survives tab switches.
  let mounted = $state<Record<TabKey, boolean>>({
    compliance: true, winscope: false, setpoint: false, ecu: false,
  });

  const visibleTabs = $derived(TABS.filter((t) => !t.xls || caps?.canXls));

  function go(key: TabKey) {
    tab = key;
    if (!mounted[key]) mounted = { ...mounted, [key]: true };
  }

  onMount(async () => {
    backend = await selectBackend();
    caps = await backend.caps();
    ready = true;
  });
</script>

<div class="shell">
  <nav class="tabbar">
    <div class="brand"><span class="bolt">⚡</span> PQA</div>
    <div class="tabs">
      {#each visibleTabs as t}
        <button class="tab" class:active={tab === t.key} onclick={() => go(t.key)}>{t.label}</button>
      {/each}
    </div>
    {#if caps}<span class="env">{caps.platform}</span>{/if}
  </nav>

  {#if ready}
    <div class="view" class:hidden={tab !== 'compliance'}>
      {#if mounted.compliance}<ComplianceView {backend} {caps} mode="csv" />{/if}
    </div>
    {#if caps?.canXls}
      <div class="view" class:hidden={tab !== 'winscope'}>
        {#if mounted.winscope}<ComplianceView {backend} {caps} mode="winscope" />{/if}
      </div>
      <div class="view" class:hidden={tab !== 'setpoint'}>
        {#if mounted.setpoint}<SetPointView {backend} {caps} />{/if}
      </div>
      <div class="view" class:hidden={tab !== 'ecu'}>
        {#if mounted.ecu}<EcuPlotView {backend} {caps} />{/if}
      </div>
    {/if}
  {:else}
    <div class="boot"><div class="bolt">⚡</div><p>Starting…</p></div>
  {/if}
</div>

<style>
  .shell { min-height: 100vh; display: flex; flex-direction: column; }
  .tabbar {
    height: 48px;
    flex: 0 0 48px;
    background: var(--navy);
    color: #e2e8f0;
    display: flex;
    align-items: stretch;
    gap: 6px;
    padding: 0 14px;
    position: sticky;
    top: 0;
    z-index: 10;
  }
  .brand { display: flex; align-items: center; gap: 6px; font-weight: 800; letter-spacing: -0.02em; color: #fff; padding-right: 10px; }
  .brand .bolt { display: grid; place-items: center; width: 26px; height: 26px; background: var(--blue); border-radius: 7px; font-size: 14px; }
  .tabs { display: flex; align-items: stretch; gap: 2px; flex: 1; }
  .tab {
    background: none;
    border: none;
    color: #94a3b8;
    font-size: 14px;
    padding: 0 14px;
    border-bottom: 2px solid transparent;
  }
  .tab:hover { color: #e2e8f0; }
  .tab.active { color: #fff; border-bottom-color: var(--blue); font-weight: 600; }
  .env { align-self: center; background: #1e293b; color: #94a3b8; font-size: 11px; padding: 2px 8px; border-radius: 999px; }
  .view { flex: 1; min-height: 0; }
  .view.hidden { display: none; }
  .boot { flex: 1; display: grid; place-items: center; gap: 10px; color: var(--text-sub); }
  .boot .bolt { font-size: 34px; opacity: 0.4; }
  @media (max-width: 640px) { .tabbar { gap: 2px; padding: 0 6px; } .tab { padding: 0 8px; font-size: 13px; } }
</style>
