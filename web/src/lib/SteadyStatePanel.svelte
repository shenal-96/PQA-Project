<script lang="ts">
  import type { AnalysisBackend } from '../backend';
  import type { Caps, SteadySummary, SteadyWindow, SteadyWindowEdit } from '../backend/types';
  import { cell, num2 } from './format';

  let { windows, summary, backend, caps }: {
    windows: SteadyWindow[];
    summary: SteadySummary | undefined;
    backend: AnalysisBackend | undefined;
    caps: Caps | undefined;
  } = $props();

  // The panel owns the displayed windows once mounted (so a Re-evaluate updates
  // the table without round-tripping through the parent). Seeded from the props;
  // reseeded only when the parent passes a brand-new array (a fresh Run Analysis).
  let data = $state<SteadyWindow[]>([]);
  let summaryData = $state<SteadySummary | undefined>(undefined);
  // Editable copy (label + boundaries) for the "confirm/adjust" hybrid flow.
  type Row = { label: string; start: string; end: string };
  let rows = $state<Row[]>([]);
  let busy = $state(false);
  let err = $state<string | undefined>(undefined);
  let lastRef: SteadyWindow[] | undefined;

  $effect(() => {
    if (windows !== lastRef) {
      lastRef = windows;
      seed(windows, summary);
    }
  });

  function seed(ws: SteadyWindow[], s?: SteadySummary) {
    data = ws;
    summaryData = s;
    rows = ws.map((w) => ({
      label: w.Load_Label ?? '',
      start: w.Start_Timestamp,
      end: w.End_Timestamp,
    }));
  }

  // "0.24% · limit 1.00%" — or just the value when there is no class limit.
  function metricText(val: number | null, limit: number | null): string {
    if (val == null) return '—';
    const v = `${num2(val)}%`;
    return limit == null ? v : `${v} · limit ${num2(limit)}%`;
  }

  const passCount = $derived(data.filter((w) => w.Status === 'Pass').length);
  const failCount = $derived(data.length - passCount);
  const huntCount = $derived(data.filter((w) => w.Hunting).length);
  const canRecalc = $derived(!!backend?.recalcSteady && caps?.platform !== 'mock');

  function bandText(w: SteadyWindow, p: 'V' | 'F'): string {
    const lo = p === 'V' ? w.V_band_lower : w.F_band_lower;
    const hi = p === 'V' ? w.V_band_upper : w.F_band_upper;
    return `${num2(lo)}–${num2(hi)}`;
  }
  function outText(n: number, pct: number | null): string {
    return n > 0 ? `${n} (${num2(pct)}%)` : '0';
  }

  async function reevaluate() {
    if (!backend?.recalcSteady) return;
    busy = true;
    err = undefined;
    try {
      const edited: SteadyWindowEdit[] = rows.map((r) => ({
        start: r.start,
        end: r.end,
        label: r.label.trim() || null,
      }));
      await applyAndRefresh(edited);
    } catch (e) {
      err = String(e);
    } finally {
      busy = false;
    }
  }

  async function resetAuto() {
    if (!backend?.recalcSteady) return;
    busy = true;
    err = undefined;
    try {
      await applyAndRefresh(undefined);
    } catch (e) {
      err = String(e);
    } finally {
      busy = false;
    }
  }

  async function applyAndRefresh(edited?: SteadyWindowEdit[]) {
    const r = await backend!.recalcSteady!(edited);
    seed(r.steady, r.steady_summary);
  }

  // Drop a window from both the displayed results and the editable set so they
  // stay index-aligned; the exclusion takes effect on the next Re-evaluate.
  function removeRow(i: number) {
    data = data.filter((_, idx) => idx !== i);
    rows = rows.filter((_, idx) => idx !== i);
  }
</script>

<div class="steady">
  <section class="cards">
    <div class="card"><span class="k">Dwells</span><span class="v">{data.length}</span></div>
    <div class="card pass"><span class="k">Pass</span><span class="v">{passCount}</span></div>
    <div class="card fail"><span class="k">Fail</span><span class="v">{failCount}</span></div>
    <div class="card warn"><span class="k">Hunting</span><span class="v">{huntCount}</span></div>
  </section>

  {#if err}<div class="banner error">{err}</div>{/if}

  {#snippet verdict(pass: boolean | null)}
    {#if pass === true}<span class="pill pass">Pass</span>
    {:else if pass === false}<span class="pill bad">Fail</span>
    {:else}<span class="pill dim">—</span>{/if}
  {/snippet}

  {#if summaryData && summaryData.n_windows > 0}
    <section class="summary">
      <div class="sum-head">
        <span class="sum-title">ISO 8528-5 summary</span>
        {#if summaryData.performance_class}
          <span class="cls">Class {summaryData.performance_class}</span>
        {:else}
          <span class="cls dim">No class · free-form δ bands</span>
        {/if}
        {#if summaryData.sample_rate_hz != null}<span class="fs">{num2(summaryData.sample_rate_hz)} Hz</span>{/if}
      </div>
      <div class="sum-grid">
        <div class="sm">
          <span class="sk">ΔU_st — voltage regulation (±)</span>
          <span class="sv">{metricText(summaryData.delta_u_st_pct, summaryData.delta_u_st_limit_pct)}</span>
          {@render verdict(summaryData.delta_u_st_pass)}
        </div>
        <div class="sm">
          <span class="sk">Frequency droop (sanity)</span>
          <span class="sv">{metricText(summaryData.freq_droop_pct, summaryData.freq_droop_limit_pct)}</span>
          {@render verdict(summaryData.freq_droop_pass)}
        </div>
        <div class="sm">
          <span class="sk">ΔU_2.0 — voltage unbalance @ no-load</span>
          <span class="sv dim">{summaryData.volt_unbalance_status}</span>
        </div>
        <div class="sm">
          <span class="sk">Û_mod,s — voltage modulation</span>
          <span class="sv dim">{summaryData.modulation_status}</span>
        </div>
      </div>
    </section>
  {/if}

  {#if data.length === 0}
    <div class="empty">No stable dwell windows detected. Lower the dwell minimum or transient-exclusion in the sidebar and re-run.</div>
  {:else}
    <div class="wrap">
      <table>
        <thead>
          <tr>
            <th>Load</th>
            <th>Window (start – end)</th>
            <th>Dur (s)</th>
            <th>Samples</th>
            <th>δU band (V)</th>
            <th>V min / mean / max</th>
            <th>V out</th>
            <th>δf band (Hz)</th>
            <th>F min / mean / max</th>
            <th>F out</th>
            <th>β_f % / lim</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each data as w, i}
            <tr class:fail={w.Status === 'Fail'}>
              <td><input class="lbl" bind:value={rows[i].label} placeholder="—" /></td>
              <td class="range">
                <input class="ts" bind:value={rows[i].start} />
                <input class="ts" bind:value={rows[i].end} />
              </td>
              <td class="mono">{num2(w.Duration_s)}</td>
              <td class="mono">{w.n_samples}</td>
              <td class="mono dim">{bandText(w, 'V')}</td>
              <td class="mono">{num2(w.V_min)} / {num2(w.V_mean)} / {num2(w.V_max)}</td>
              <td class="mono" class:bad={w.V_n_out > 0}>{outText(w.V_n_out, w.V_pct_out)}</td>
              <td class="mono dim">{bandText(w, 'F')}</td>
              <td class="mono">{num2(w.F_min)} / {num2(w.F_mean)} / {num2(w.F_max)}</td>
              <td class="mono" class:bad={w.F_n_out > 0}>{outText(w.F_n_out, w.F_pct_out)}</td>
              <td class="mono">
                {#if w.Beta_f_pct == null}—{:else}<span class:bad={w.Beta_f_pass === false} class:ok={w.Beta_f_pass === true}>{num2(w.Beta_f_pct)}</span>{#if w.Beta_f_limit_pct != null}<span class="dim"> / {num2(w.Beta_f_limit_pct)}</span>{/if}{/if}
              </td>
              <td>
                <span class="pill" class:pass={w.Status === 'Pass'} class:bad={w.Status === 'Fail'}>{cell(w.Status)}</span>
                {#if w.Hunting}<span class="pill warn" title={w.Hunting_Reasons}>⚠ Hunting</span>{/if}
              </td>
              <td>{#if rows[i]}<button class="rm" title="Remove window" onclick={() => removeRow(i)}>✕</button>{/if}</td>
            </tr>
            {#if w.Status === 'Fail' || w.Hunting}
              <tr class="notes-row" class:fail={w.Status === 'Fail'}>
                <td colspan="13" class="notes">
                  {#if w.Failure_Reasons}{w.Failure_Reasons}{/if}
                  {#if w.Hunting_Reasons}{w.Failure_Reasons ? ' · ' : ''}⚠ {w.Hunting_Reasons}{/if}
                </td>
              </tr>
            {/if}
          {/each}
        </tbody>
      </table>
    </div>

    <div class="actions">
      <button class="btn" onclick={reevaluate} disabled={!canRecalc || busy}>
        {busy ? 'Re-evaluating…' : '↺ Re-evaluate windows'}
      </button>
      <button class="btn ghost" onclick={resetAuto} disabled={!canRecalc || busy}>Reset to auto-detected</button>
      {#if !canRecalc}
        <span class="muted">Editing dwell windows runs in the desktop app.</span>
      {:else}
        <span class="muted">Adjust each window's label or start/end, then re-evaluate against the δ bands.</span>
      {/if}
    </div>
  {/if}
</div>

<style>
  .steady { display: flex; flex-direction: column; gap: 12px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; }
  .card { background: var(--navy); border: 1px solid #1e293b; border-radius: 10px; padding: 12px 14px; display: flex; flex-direction: column; gap: 4px; color: #e2e8f0; }
  .card .k { font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
  .card .v { font-size: 24px; font-weight: 700; }
  .card.pass { border-color: var(--green); } .card.pass .v { color: #4ade80; }
  .card.fail { border-color: var(--red); } .card.fail .v { color: #f87171; }
  .card.warn { border-color: var(--amber); } .card.warn .v { color: #fbbf24; }
  .banner.error { background: #fee2e2; color: #b91c1c; padding: 10px 14px; border-radius: 8px; font-size: 13px; }
  .empty { padding: 18px; border: 2px dashed var(--border); border-radius: 10px; color: var(--text-sub); font-size: 13px; }

  /* Cross-window ISO 8528-5 summary (ΔU_st, droop, unbalance/modulation gate). */
  .summary { border: 1px solid var(--border); border-radius: 10px; background: var(--card); padding: 12px 14px; }
  .sum-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
  .sum-title { font-weight: 700; font-size: 13px; color: var(--text-main); }
  .cls { font-size: 11px; font-weight: 600; padding: 2px 9px; border-radius: 999px; background: #e0e7ff; color: #3730a3; }
  .cls.dim { background: #f1f5f9; color: #64748b; }
  .fs { font-family: "JetBrains Mono", monospace; font-size: 11.5px; color: var(--text-sub); }
  .sum-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 8px 18px; }
  .sm { display: flex; align-items: center; gap: 8px; font-size: 12.5px; }
  .sk { color: var(--text-sub); }
  .sv { font-family: "JetBrains Mono", monospace; color: var(--text-main); margin-left: auto; }
  .sv.dim { font-style: italic; }

  .wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; background: var(--card); }
  table { border-collapse: collapse; width: 100%; font-size: 12.5px; }
  th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }
  th { background: #f1f5f9; color: var(--text-sub); font-weight: 600; text-transform: uppercase; font-size: 10.5px; letter-spacing: 0.04em; }
  tr.fail { background: #fef2f2; }
  tr.notes-row td { padding-top: 0; }
  .notes { color: var(--text-sub); font-size: 12px; white-space: normal; }
  .mono { font-family: "JetBrains Mono", monospace; }
  .dim { color: var(--text-sub); }
  .bad { color: #b91c1c; font-weight: 600; }
  .ok { color: #15803d; font-weight: 600; }
  .range { display: flex; flex-direction: column; gap: 3px; }
  input.lbl { width: 70px; }
  input.ts { width: 150px; font-family: "JetBrains Mono", monospace; font-size: 11px; }
  input { background: #fff; border: 1px solid var(--border); border-radius: 6px; padding: 4px 6px; font-size: 12px; }
  input:focus { outline: none; border-color: var(--blue); }
  .pill { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 11.5px; font-weight: 600; }
  .pill.pass { background: #dcfce7; color: #15803d; }
  .pill.bad { background: #fee2e2; color: #b91c1c; }
  .pill.warn { background: #fffbeb; color: #b45309; margin-left: 5px; }
  .pill.dim { background: #f1f5f9; color: #64748b; }
  .rm { background: none; border: none; color: #94a3b8; cursor: pointer; font-size: 13px; }
  .rm:hover { color: #b91c1c; }
  .actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .btn { background: #0d9488; color: #fff; border: none; padding: 9px 16px; border-radius: 8px; font-weight: 700; cursor: pointer; font-size: 13px; }
  .btn.ghost { background: none; color: #0d9488; border: 1px solid #0d9488; font-weight: 600; }
  .btn:disabled { background: #cbd5e1; color: #fff; border-color: #cbd5e1; cursor: not-allowed; }
  .muted { color: var(--text-sub); font-size: 12px; }
</style>
