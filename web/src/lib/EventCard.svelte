<script lang="ts">
  import type { EventRecord, EventOverride, SnapshotData, SnapshotOpts } from '../backend/types';
  import { cell, num2 } from './format';
  import SnapshotChart from './SnapshotChart.svelte';
  import type { SnapshotShow } from './SnapshotChart.svelte';

  let {
    event,
    index,
    snap,
    show,
    onApply,
    onOverride,
  }: {
    event: EventRecord;
    index: number;
    snap: SnapshotData | null;
    show?: SnapshotShow;
    onApply: (i: number, opts: SnapshotOpts) => void;
    onOverride: (i: number, ov: EventOverride) => void;
  } = $props();

  let open = $state(false);

  // Per-snapshot window / time-shift inputs.
  let windowS = $state<number | undefined>(undefined);
  let timeOffset = $state(0);

  // Per-event override inputs.
  let vExitOffset = $state(0);
  let vRecOn = $state(false);
  let vRecVal = $state(0);
  let fExitOffset = $state(0);
  let fRecOn = $state(false);
  let fRecVal = $state(0);

  const isPass = $derived(String(event['Compliance_Status'] ?? '').toLowerCase() === 'pass');
  const isFault = $derived(event['Potential_Fault'] === true);

  function applyWindow() {
    onApply(index, { window_s: windowS, time_offset_s: timeOffset });
  }
  function resetWindow() {
    windowS = undefined;
    timeOffset = 0;
    onApply(index, {});
  }
  function emitOverride() {
    onOverride(index, {
      v_exit_offset: vExitOffset,
      v_rec_override: vRecOn ? vRecVal : null,
      f_exit_offset: fExitOffset,
      f_rec_override: fRecOn ? fRecVal : null,
    });
  }
</script>

<details class="card" bind:open class:fail={!isPass}>
  <summary>
    <span class="pill" class:pass={isPass} class:bad={!isPass}>{cell(event['Compliance_Status'])}</span>
    {#if isFault}<span class="pill warn">⚠</span>{/if}
    <span class="dkw">{Number(event['dKw']) >= 0 ? '+' : ''}{num2(event['dKw'])} kW</span>
    <span class="ts">{cell(event['Start_Timestamp'])}</span>
  </summary>

  {#if open}
    {#if snap}
      <SnapshotChart {snap} {show} />
    {:else}
      <div class="placeholder">Snapshot rendering…</div>
    {/if}

    <div class="controls">
      <div class="group">
        <span class="lbl">Snapshot view</span>
        <label>Window (s)<input type="number" min="3" step="1" bind:value={windowS} placeholder="auto" /></label>
        <label>Time-shift (s)<input type="number" step="0.5" bind:value={timeOffset} /></label>
        <button class="apply" onclick={applyWindow}>↺ Apply</button>
        <button class="reset" onclick={resetWindow}>⟲ Reset</button>
      </div>

      <div class="group">
        <span class="lbl">Voltage override</span>
        <label>Exit shift (s)<input type="number" step="0.1" bind:value={vExitOffset} onchange={emitOverride} /></label>
        <label class="chk"><input type="checkbox" bind:checked={vRecOn} onchange={emitOverride} /> Set recovery (s)</label>
        <input type="number" step="0.1" bind:value={vRecVal} disabled={!vRecOn} onchange={emitOverride} />
      </div>

      <div class="group">
        <span class="lbl">Frequency override</span>
        <label>Exit shift (s)<input type="number" step="0.1" bind:value={fExitOffset} onchange={emitOverride} /></label>
        <label class="chk"><input type="checkbox" bind:checked={fRecOn} onchange={emitOverride} /> Set recovery (s)</label>
        <input type="number" step="0.1" bind:value={fRecVal} disabled={!fRecOn} onchange={emitOverride} />
      </div>
    </div>
  {/if}
</details>

<style>
  .card { border: 1px solid var(--border); border-radius: 10px; background: var(--card); padding: 0 14px; }
  .card.fail { border-color: #fecaca; }
  summary { display: flex; align-items: center; gap: 12px; padding: 12px 4px; cursor: pointer; list-style: none; }
  summary::-webkit-details-marker { display: none; }
  .pill { padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
  .pill.pass { background: #dcfce7; color: #15803d; }
  .pill.bad { background: #fee2e2; color: #b91c1c; }
  .pill.warn { background: #fffbeb; color: #b45309; }
  .dkw { font-family: "JetBrains Mono", monospace; font-weight: 600; }
  .ts { color: var(--text-sub); font-family: "JetBrains Mono", monospace; font-size: 13px; margin-left: auto; }
  .placeholder { padding: 40px; text-align: center; color: var(--text-sub); }
  .controls { display: flex; flex-wrap: wrap; gap: 16px; padding: 8px 4px 16px; }
  .group { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; background: #f8fafc; border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; }
  .group .lbl { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-sub); font-weight: 600; }
  label { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #334155; }
  label.chk { gap: 4px; }
  input[type="number"] { width: 84px; padding: 5px 7px; border: 1px solid var(--border); border-radius: 6px; font-family: "JetBrains Mono", monospace; font-size: 12px; }
  input[type="number"]:disabled { background: #f1f5f9; color: #94a3b8; }
  button { border: none; border-radius: 7px; padding: 6px 12px; font-size: 12px; font-weight: 600; cursor: pointer; }
  .apply { background: var(--blue); color: #fff; }
  .reset { background: #e2e8f0; color: #334155; }
</style>
