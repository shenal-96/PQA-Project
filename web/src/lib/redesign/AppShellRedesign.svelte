<script lang="ts">
  import type { AnalysisBackend } from '../../backend';
  import type { Caps } from '../../backend/types';
  import ComplianceView from '../ComplianceView.svelte';
  import SetPointView from '../SetPointView.svelte';
  import EcuPlotView from '../EcuPlotView.svelte';
  import SettingsReferenceView from '../SettingsReferenceView.svelte';
  import CrashPrompt from '../CrashPrompt.svelte';
  import HelpDialog from '../HelpDialog.svelte';
  import ChangelogDialog from '../ChangelogDialog.svelte';
  import { APP_VERSION } from '../../config/changelog';
  import { toggleTheme } from '../../theme/theme.svelte';
  import Icon from './Icon.svelte';

  // Dark redesign shell. Owns its own copy of the tab state machine so the
  // classic shell in App.svelte stays untouched (prototype duplication, per
  // docs/redesign/PLAN.md §6 Phase 2). Reuses every view component + the real
  // backend; only the chrome is new. Inner content (sidebar + results) is still
  // classic-styled until Phases 3–4.
  let { backend, caps, ready }: {
    backend: AnalysisBackend | undefined;
    caps: Caps | undefined;
    ready: boolean;
  } = $props();

  type TabKey = 'compliance' | 'winscope' | 'setpoint' | 'ecu' | 'settings';
  type IconName = 'bolt' | 'scope' | 'wrench' | 'chart' | 'book';
  const TABS: { key: TabKey; label: string; icon: IconName; xls: boolean }[] = [
    { key: 'compliance', label: 'Compliance', icon: 'bolt', xls: false },
    { key: 'winscope', label: 'WinScope', icon: 'scope', xls: true },
    { key: 'setpoint', label: 'Set Point', icon: 'wrench', xls: true },
    { key: 'ecu', label: 'ECU Plotting', icon: 'chart', xls: true },
    { key: 'settings', label: 'Settings Reference', icon: 'book', xls: false },
  ];

  let tab = $state<TabKey>('compliance');
  let helpOpen = $state(false);
  let changelogOpen = $state(false);
  // Lazy-mount each view on first visit, then keep it mounted (hidden) so its
  // state survives tab switches — mirrors App.svelte.
  let mounted = $state<Record<TabKey, boolean>>({
    compliance: true, winscope: false, setpoint: false, ecu: false, settings: false,
  });

  const visibleTabs = $derived(TABS.filter((t) => !t.xls || caps?.canXls));

  function go(key: TabKey) {
    tab = key;
    if (!mounted[key]) mounted = { ...mounted, [key]: true };
  }
</script>

<div class="rd-shell">
  <header class="rd-topbar">
    <div class="rd-brand">
      <span class="rd-logo"><Icon name="bolt" /></span>
      <span class="rd-wordmark">PQA <span class="rd-dim">PROJECT</span></span>
      <button class="rd-ver mono" onclick={() => (changelogOpen = true)} title="View version history & send feedback">{APP_VERSION}</button>
    </div>

    <nav class="rd-nav" aria-label="Main navigation">
      {#each visibleTabs as t}
        <button class="rd-tab" class:active={tab === t.key} onclick={() => go(t.key)}>
          <span class="rd-tab-ic"><Icon name={t.icon} /></span>
          {t.label}
          {#if tab === t.key}<span class="rd-tab-underline"></span>{/if}
        </button>
      {/each}
    </nav>

    <div class="rd-actions">
      <button class="rd-pill" onclick={toggleTheme} title="Switch back to the classic look">☀ Classic</button>
      <button class="rd-pill" onclick={() => (helpOpen = true)} title="Open the user guide">
        <span class="rd-pill-ic"><Icon name="help" /></span> Help
      </button>
      {#if caps}<span class="rd-pill rd-status"><span class="rd-dot"></span>{caps.platform}</span>{/if}
    </div>
  </header>

  {#if helpOpen}<HelpDialog onClose={() => (helpOpen = false)} />{/if}
  {#if changelogOpen}<ChangelogDialog {backend} onClose={() => (changelogOpen = false)} />{/if}

  {#if ready}
    <div class="rd-view" class:hidden={tab !== 'compliance'}>
      {#if mounted.compliance}<ComplianceView {backend} {caps} mode="csv" />{/if}
    </div>
    {#if caps?.canXls}
      <div class="rd-view" class:hidden={tab !== 'winscope'}>
        {#if mounted.winscope}<ComplianceView {backend} {caps} mode="winscope" />{/if}
      </div>
      <div class="rd-view" class:hidden={tab !== 'setpoint'}>
        {#if mounted.setpoint}<SetPointView {backend} {caps} />{/if}
      </div>
      <div class="rd-view" class:hidden={tab !== 'ecu'}>
        {#if mounted.ecu}<EcuPlotView {backend} {caps} />{/if}
      </div>
    {/if}
    <div class="rd-view" class:hidden={tab !== 'settings'}>
      {#if mounted.settings}<SettingsReferenceView {backend} {caps} />{/if}
    </div>
  {:else}
    <div class="rd-boot"><span class="rd-boot-bolt"><Icon name="bolt" size={34} /></span><p>Starting…</p></div>
  {/if}

  {#if backend}<CrashPrompt {backend} />{/if}
</div>

<style>
  .rd-shell { height: 100vh; display: flex; flex-direction: column; overflow: hidden; background: var(--bg-main); }

  .rd-topbar {
    height: 56px; flex: 0 0 56px; display: flex; align-items: center; gap: 4px;
    padding: 0 18px; background: var(--bg); border-bottom: 1px solid var(--line);
  }

  .rd-brand { display: flex; align-items: center; gap: 11px; padding-right: 18px; }
  .rd-logo {
    width: 32px; height: 32px; border-radius: 9px; display: grid; place-items: center;
    color: #fff; background: linear-gradient(150deg, #3f7bff, #2052e6);
    box-shadow: 0 2px 10px rgba(47, 107, 255, 0.4);
  }
  .rd-wordmark { font-weight: 800; font-size: 16px; letter-spacing: 0.02em; color: var(--ink); }
  .rd-dim { color: var(--sub); }
  .rd-ver {
    font-size: 10.5px; color: var(--mute); background: var(--panel-2);
    border: 1px solid var(--line); border-radius: 6px; padding: 2px 7px; cursor: pointer;
    transition: background 120ms, color 120ms;
  }
  .rd-ver:hover { background: var(--blue); color: #fff; border-color: var(--blue); }

  .rd-nav { display: flex; align-items: center; gap: 2px; height: 100%; }
  .rd-tab {
    display: flex; align-items: center; gap: 8px; padding: 0 16px; height: 100%;
    background: none; border: none; cursor: pointer; position: relative;
    color: var(--sub); font-size: 13.5px; font-weight: 500;
  }
  .rd-tab:hover { color: var(--ink); }
  .rd-tab-ic { color: var(--mute); display: grid; place-items: center; }
  .rd-tab.active { color: var(--ink); font-weight: 600; }
  .rd-tab.active .rd-tab-ic { color: var(--blue); }
  .rd-tab-underline { position: absolute; left: 12px; right: 12px; bottom: 0; height: 2.5px; background: var(--blue); border-radius: 2px; }

  .rd-actions { margin-left: auto; display: flex; align-items: center; gap: 8px; }
  .rd-pill {
    display: flex; align-items: center; gap: 7px; height: 32px; padding: 0 13px;
    background: var(--panel); border: 1px solid var(--line-2); border-radius: 8px;
    color: var(--ink); font-size: 12.5px; font-weight: 500; cursor: pointer;
  }
  .rd-pill:hover { background: var(--panel-3); }
  .rd-pill-ic { color: var(--mute); display: grid; place-items: center; }
  .rd-status { cursor: default; }
  .rd-status:hover { background: var(--panel); }
  .rd-dot { width: 7px; height: 7px; border-radius: 99px; background: var(--green); box-shadow: 0 0 7px var(--green); }

  .rd-view { flex: 1; min-height: 0; overflow: hidden; }
  .rd-view.hidden { display: none; }
  .rd-boot { flex: 1; display: grid; place-items: center; gap: 10px; color: var(--sub); }
  .rd-boot-bolt { color: var(--blue); opacity: 0.5; }

  /* Narrow: drop the fixed-height split, let the page scroll (mirrors classic). */
  @media (max-width: 820px) {
    .rd-shell { height: auto; min-height: 100vh; overflow: visible; }
    .rd-view { overflow: visible; }
  }
  @media (max-width: 640px) {
    .rd-topbar { gap: 2px; padding: 0 8px; }
    .rd-tab { padding: 0 9px; font-size: 13px; }
    .rd-brand { padding-right: 8px; }
  }
</style>
