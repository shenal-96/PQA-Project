<script lang="ts">
  import type { AnalysisBackend } from '../backend';
  import type {
    Caps, ReferenceDevice, ReferenceSetting, SettingsReference,
  } from '../backend/types';

  let { backend, caps }: { backend: AnalysisBackend | undefined; caps: Caps | undefined } = $props();

  let data = $state<SettingsReference | undefined>(undefined);
  let busy = $state(false);
  let error = $state<string | undefined>(undefined);

  let device = $state('All devices'); // 'All devices' | device name
  let query = $state('');
  // Track which group cards are open (keyed by `${device}∷${group}`).
  let open = $state<Record<string, boolean>>({});

  const deviceNames = $derived(data ? data.devices.map((d) => d.name) : []);
  const anyUnverified = $derived(data ? data.devices.some((d) => !d.verified) : false);

  // Devices in scope after the device filter.
  const scopedDevices = $derived<ReferenceDevice[]>(
    data
      ? device === 'All devices'
        ? data.devices
        : data.devices.filter((d) => d.name === device)
      : [],
  );

  const terms = $derived(query.trim().toLowerCase().split(/\s+/).filter(Boolean));

  function matches(s: ReferenceSetting, group: string): boolean {
    if (terms.length === 0) return true;
    const hay = `${group} ${s.name} ${s.description} ${s.philosophy} ${s.performance}`.toLowerCase();
    return terms.every((t) => hay.includes(t));
  }

  // Flat search results across scoped devices when a query is present.
  type Hit = { device: string; group: string; setting: ReferenceSetting };
  const hits = $derived.by<Hit[]>(() => {
    const out: Hit[] = [];
    for (const dev of scopedDevices) {
      for (const g of dev.groups) {
        for (const s of g.settings) {
          if (matches(s, g.name)) out.push({ device: dev.name, group: g.name, setting: s });
        }
      }
    }
    return out;
  });

  function key(devName: string, group: string): string {
    return `${devName}∷${group}`;
  }
  function toggle(devName: string, group: string) {
    const k = key(devName, group);
    open = { ...open, [k]: !open[k] };
  }

  async function load() {
    if (!backend?.settingsReference) {
      error = 'Settings Reference runs in the desktop app.';
      return;
    }
    busy = true;
    error = undefined;
    try {
      data = await backend.settingsReference();
    } catch (e) {
      error = String(e);
    } finally {
      busy = false;
    }
  }

  // Load once on mount (the view is lazy-mounted by App.svelte).
  $effect(() => {
    if (!data && !busy && !error) load();
  });
</script>

<main class="wrap">
  <div class="head">
    <span class="bar"></span>
    <h2>Settings Reference</h2>
    <span class="sub">ComAp InteliGen / Leroy-Somer D550 — what each setting does, the control philosophy, and its performance effect</span>
  </div>

  {#if anyUnverified}
    <div class="banner warn">
      <strong>⚠ Curated starting reference.</strong> Ranges, defaults and exact setpoint names are indicative and
      must be verified against the official ComAp InteliGen / InteliConfig and Leroy-Somer D550 manuals before
      relying on them in the field.
    </div>
  {/if}

  {#if error}<div class="banner error">{error}</div>{/if}

  {#if busy && !data}
    <div class="empty"><div class="bolt">📖</div><p>Loading reference…</p></div>
  {:else if data}
    <div class="controls">
      <div class="seg">
        <button class:on={device === 'All devices'} onclick={() => (device = 'All devices')}>All devices</button>
        {#each deviceNames as name}
          <button class:on={device === name} onclick={() => (device = name)}>{name}</button>
        {/each}
      </div>
      <input
        class="filter"
        type="text"
        bind:value={query}
        placeholder="Search settings — e.g. 'overload', 'PID', 'frequency recovery', 'droop'…"
      />
      <span class="count">{data.count} settings · {data.devices.length} devices</span>
    </div>

    {#if terms.length}
      <!-- Search view: flat list across the scoped device(s). -->
      <div class="results-head">{hits.length} setting{hits.length === 1 ? '' : 's'} match “{query.trim()}”</div>
      {#if hits.length === 0}
        <div class="empty"><p>No matching settings. Try a broader term (e.g. 'voltage', 'crank', 'gain').</p></div>
      {:else}
        <div class="cards">
          {#each hits as h (h.device + '∷' + h.group + '∷' + h.setting.name)}
            <div class="card">
              <div class="card-top">
                <div class="card-name">{h.setting.name}{#if h.setting.units}<span class="units"> · {h.setting.units}</span>{/if}</div>
                <div class="tags">
                  <span class="tag dev">{h.device}</span>
                  <span class="tag grp">{h.group}</span>
                </div>
              </div>
              <div class="rd">
                <span><b>Range:</b> {h.setting.range}</span>
                <span><b>Default:</b> {h.setting.default}</span>
              </div>
              <div class="desc">{h.setting.description}</div>
              <div class="note philosophy"><b>Control philosophy — </b>{h.setting.philosophy}</div>
              <div class="note performance"><b>Performance effect — </b>{h.setting.performance}</div>
            </div>
          {/each}
        </div>
      {/if}
    {:else}
      <!-- Browse view: device(s) with grouped, expandable sections. -->
      {#each scopedDevices as dev (dev.name)}
        <div class="device">
          <div class="device-head">
            <div class="device-name">{dev.name}</div>
            <div class="device-summary">{dev.summary}</div>
            <div class="device-source">
              Source: {dev.source}
              {#if !dev.verified}<span class="unverified">· unverified</span>{/if}
            </div>
          </div>
          {#each dev.groups as g (g.name)}
            <div class="group">
              <button class="group-head" onclick={() => toggle(dev.name, g.name)}>
                <span class="chev" class:open={open[key(dev.name, g.name)]}>▸</span>
                <span class="group-name">{g.name}</span>
                <span class="group-count">{g.settings.length} settings</span>
              </button>
              {#if open[key(dev.name, g.name)]}
                <div class="cards">
                  {#each g.settings as s (s.name)}
                    <div class="card">
                      <div class="card-top">
                        <div class="card-name">{s.name}{#if s.units}<span class="units"> · {s.units}</span>{/if}</div>
                      </div>
                      <div class="rd">
                        <span><b>Range:</b> {s.range}</span>
                        <span><b>Default:</b> {s.default}</span>
                      </div>
                      <div class="desc">{s.description}</div>
                      <div class="note philosophy"><b>Control philosophy — </b>{s.philosophy}</div>
                      <div class="note performance"><b>Performance effect — </b>{s.performance}</div>
                    </div>
                  {/each}
                </div>
              {/if}
            </div>
          {/each}
        </div>
      {/each}
    {/if}
  {/if}
</main>

<style>
  .wrap { height: 100%; overflow-y: auto; padding: clamp(1rem, 2.5vw, 2rem); display: flex; flex-direction: column; gap: 16px; }
  .wrap > :global(*) { flex-shrink: 0; }
  .head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .head .bar { width: 4px; height: 22px; border-radius: 2px; background: var(--cyan, #0891b2); }
  h2 { margin: 0; font-size: 1.2rem; }
  .sub { color: var(--text-sub); font-size: 13px; }
  .banner { padding: 10px 14px; border-radius: 8px; font-size: 13px; line-height: 1.5; }
  .banner.warn { background: #fffbeb; border: 1px solid #fcd34d; border-left: 4px solid #f59e0b; color: #92400e; }
  .banner.error { background: #fee2e2; color: #b91c1c; }
  .controls { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .seg { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; flex-wrap: wrap; }
  .seg button { background: #fff; border: none; padding: 8px 14px; font-size: 13px; color: var(--text-sub); }
  .seg button.on { background: var(--blue); color: #fff; font-weight: 600; }
  .filter { flex: 1 1 260px; min-width: 220px; border: 1px solid var(--border); border-radius: 7px; padding: 8px 11px; font-size: 13px; }
  .count { font-size: 12px; color: var(--text-sub); font-family: 'JetBrains Mono', monospace; }
  .results-head { font-size: 13px; color: var(--text-sub); }

  .device { display: flex; flex-direction: column; gap: 8px; }
  .device-head { padding-bottom: 4px; }
  .device-name { font-size: 1.05rem; font-weight: 800; color: var(--navy, #0f172a); }
  .device-summary { font-size: 13px; color: var(--text-sub); margin-top: 2px; }
  .device-source { font-size: 11px; color: #94a3b8; margin-top: 2px; }
  .unverified { color: #b45309; font-weight: 600; }

  .group { border: 1px solid var(--border); border-radius: 10px; background: var(--card, #fff); overflow: hidden; }
  .group-head { width: 100%; display: flex; align-items: center; gap: 10px; background: #f8fafc; border: none; padding: 11px 14px; font-size: 13px; color: var(--navy, #0f172a); cursor: pointer; text-align: left; }
  .group-head:hover { background: #f1f5f9; }
  .chev { display: inline-block; transition: transform 0.15s; color: var(--text-sub); }
  .chev.open { transform: rotate(90deg); }
  .group-name { font-weight: 700; }
  .group-count { margin-left: auto; font-size: 11px; color: var(--text-sub); font-family: 'JetBrains Mono', monospace; }

  .cards { display: flex; flex-direction: column; gap: 10px; padding: 12px; }
  .card { border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; background: var(--card, #fff); box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }
  .card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap; }
  .card-name { font-size: 1rem; font-weight: 700; color: var(--navy, #0f172a); }
  .units { color: var(--text-sub); font-weight: 500; font-size: 0.85rem; }
  .tags { display: flex; gap: 6px; flex-wrap: wrap; }
  .tag { border-radius: 6px; padding: 2px 8px; font-size: 11px; font-weight: 600; }
  .tag.dev { background: #eff6ff; color: #1d4ed8; }
  .tag.grp { background: #f1f5f9; color: #475569; }
  .rd { display: flex; gap: 18px; flex-wrap: wrap; margin: 8px 0 10px; font-size: 12.5px; color: #475569; }
  .rd b { color: var(--navy, #0f172a); }
  .desc { font-size: 13.5px; color: #334155; line-height: 1.5; margin-bottom: 8px; }
  .note { font-size: 13px; color: #334155; line-height: 1.5; padding-left: 11px; margin-bottom: 6px; }
  .note.philosophy { border-left: 3px solid var(--cyan, #0891b2); }
  .note.philosophy b { color: #0e7490; }
  .note.performance { border-left: 3px solid var(--purple, #9333ea); }
  .note.performance b { color: #7e22ce; }
  .note:last-child { margin-bottom: 0; }

  .empty { display: grid; place-items: center; gap: 10px; padding: 50px 0; color: var(--text-sub); border: 2px dashed var(--border); border-radius: 12px; }
  .empty .bolt { font-size: 30px; opacity: 0.4; }
</style>
