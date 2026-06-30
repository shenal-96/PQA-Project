<script lang="ts">
  import { onMount } from 'svelte';
  import { selectBackend } from './backend';
  import type { AnalysisBackend } from './backend';
  import type { Caps } from './backend/types';
  import ComplianceView from './lib/ComplianceView.svelte';
  import SetPointView from './lib/SetPointView.svelte';
  import EcuPlotView from './lib/EcuPlotView.svelte';
  import SettingsReferenceView from './lib/SettingsReferenceView.svelte';
  import CrashPrompt from './lib/CrashPrompt.svelte';
  import HelpDialog from './lib/HelpDialog.svelte';
  import ChangelogDialog from './lib/ChangelogDialog.svelte';
  import { APP_VERSION } from './config/changelog';
  import { themeState, toggleTheme } from './theme/theme.svelte';
  import AppShellRedesign from './lib/redesign/AppShellRedesign.svelte';

  let backend = $state<AnalysisBackend | undefined>(undefined);
  let caps = $state<Caps | undefined>(undefined);
  let ready = $state(false);

  type TabKey = 'compliance' | 'winscope' | 'setpoint' | 'ecu' | 'settings';
  const TABS: { key: TabKey; label: string; xls: boolean }[] = [
    { key: 'compliance', label: '⚡ Compliance', xls: false },
    { key: 'winscope', label: '📊 WinScope', xls: true },
    { key: 'setpoint', label: '🔧 Set Point', xls: true },
    { key: 'ecu', label: '🔌 ECU Plotting', xls: true },
    { key: 'settings', label: '📖 Settings Reference', xls: false },
  ];

  let tab = $state<TabKey>('compliance');
  let helpOpen = $state(false);
  let changelogOpen = $state(false);
  // Lazy-mount each view on first visit, then keep it mounted (hidden) so its
  // state (loaded file, analysis, plots) survives tab switches.
  let mounted = $state<Record<TabKey, boolean>>({
    compliance: true, winscope: false, setpoint: false, ecu: false, settings: false,
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

  // Files dropped outside a drop zone must not navigate the webview to file://.
  // The zones (use:dropzone) preventDefault on their own targets; this swallows
  // the default everywhere else.
  $effect(() => {
    const swallow = (e: DragEvent) => e.preventDefault();
    window.addEventListener('dragover', swallow);
    window.addEventListener('drop', swallow);
    return () => {
      window.removeEventListener('dragover', swallow);
      window.removeEventListener('drop', swallow);
    };
  });
</script>

{#if themeState.current === 'redesign'}
  <AppShellRedesign {backend} {caps} {ready} />
{:else}
<div class="shell">
  <nav class="tabbar">
    <div class="brand">
      <span class="bolt">⚡</span> PQA PROJECT
      <button class="ver" onclick={() => (changelogOpen = true)} title="View version history & send feedback">{APP_VERSION}</button>
    </div>
    <div class="tabs">
      {#each visibleTabs as t}
        <button class="tab" class:active={tab === t.key} onclick={() => go(t.key)}>{t.label}</button>
      {/each}
    </div>
    <button class="theme-toggle" onclick={toggleTheme} title="Try the redesign theme (prototype)">🌙 Redesign</button>
    <button class="help-btn" onclick={() => (helpOpen = true)} title="Open the user guide">❔ Help</button>
    {#if caps}<span class="env">{caps.platform}</span>{/if}
  </nav>

  {#if helpOpen}<HelpDialog onClose={() => (helpOpen = false)} />{/if}
  {#if changelogOpen}<ChangelogDialog {backend} onClose={() => (changelogOpen = false)} />{/if}

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
    <div class="view" class:hidden={tab !== 'settings'}>
      {#if mounted.settings}<SettingsReferenceView {backend} {caps} />{/if}
    </div>
  {:else}
    <div class="boot"><div class="bolt">⚡</div><p>Starting…</p></div>
  {/if}

  {#if backend}<CrashPrompt {backend} />{/if}
</div>
{/if}

<style>
  .shell { height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
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
  .brand .ver {
    margin-left: 6px; font-weight: 600; font-size: 11px; color: #94a3b8;
    background: #1e293b; padding: 2px 8px; border-radius: 999px; letter-spacing: 0;
    border: none; cursor: pointer; font-family: inherit;
    transition: background 120ms, color 120ms;
  }
  .brand .ver:hover { background: var(--blue); color: #fff; }
  .brand .ver:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }
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
  .help-btn { align-self: center; background: #1e293b; color: #cbd5e1; border: none; font-size: 13px; padding: 6px 12px; border-radius: 8px; cursor: pointer; margin-right: 8px; }
  .help-btn:hover { background: #334155; color: #fff; }
  .theme-toggle {
    align-self: center; background: #1e293b; color: #cbd5e1; border: none;
    font-size: 12px; padding: 6px 10px; border-radius: 8px; cursor: pointer;
    margin-right: 8px; white-space: nowrap;
  }
  .theme-toggle:hover { background: #334155; color: #fff; }
  .env { align-self: center; background: #1e293b; color: #94a3b8; font-size: 11px; padding: 2px 8px; border-radius: 999px; }
  .view { flex: 1; min-height: 0; overflow: hidden; }
  .view.hidden { display: none; }
  .boot { flex: 1; display: grid; place-items: center; gap: 10px; color: var(--text-sub); }
  .boot .bolt { font-size: 34px; opacity: 0.4; }
  /* Narrow: drop the fixed-height split and let the page scroll naturally. */
  @media (max-width: 820px) { .shell { height: auto; min-height: 100vh; overflow: visible; } .view { overflow: visible; } }
  @media (max-width: 640px) { .tabbar { gap: 2px; padding: 0 6px; } .tab { padding: 0 8px; font-size: 13px; } }
</style>
