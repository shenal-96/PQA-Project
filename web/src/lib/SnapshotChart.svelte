<script lang="ts">
  import { onMount } from 'svelte';
  import * as echarts from 'echarts';
  import type { SnapshotData, SnapshotPanel } from '../backend/types';
  import { fmt2 } from './format';

  export interface SnapshotShow {
    band: boolean;        // tolerance band lines
    limit: boolean;       // max-deviation limit line
    intersections: boolean; // exit + recovery markers
    extreme: boolean;     // peak-deviation marker
  }

  let { snap, show }: { snap: SnapshotData; show?: SnapshotShow } = $props();
  const SHOW = $derived<SnapshotShow>(show ?? { band: true, limit: true, intersections: true, extreme: true });

  let el: HTMLDivElement;
  let chart: echarts.ECharts | undefined;

  const ORDER: Array<keyof SnapshotData['panels']> = ['voltage', 'current', 'frequency', 'power'];
  const TOPS = ['4%', '28%', '52%', '76%'];
  const GRID_H = '17%';

  // Legend/key for the snapshot overlays — mirrors the matplotlib report-snapshot
  // legend (PR #9). A chip shows only when its display toggle is on AND at least one
  // panel actually carries that element, so the key never advertises something the
  // chart isn't drawing (e.g. the ISO β_f start band only appears in ISO dual-band mode).
  const legend = $derived.by(() => {
    const s = snap;
    const any = (pred: (p: SnapshotPanel) => boolean) =>
      ORDER.some((k) => { const p = s?.panels?.[k]; return p ? pred(p) : false; });
    return {
      band: SHOW.band && any((p) => !!p.band),
      startBand: SHOW.band && any((p) => !!p.start_band),
      limit: SHOW.limit && any((p) => !!p.limit),
      exit: SHOW.intersections && any((p) => p.exit?.ts != null && p.exit?.value != null),
      recovery: SHOW.intersections && any((p) => p.recovery?.ts != null && p.recovery?.value != null),
      extreme: SHOW.extreme && any((p) => p.extreme?.ts != null && p.extreme?.value != null),
    };
  });
  const hasLegend = $derived(
    legend.band || legend.startBand || legend.limit || legend.exit || legend.recovery || legend.extreme,
  );

  function pairs(p: SnapshotPanel) {
    return p.timestamps.map((t, i) => [t, p.values[i]]);
  }

  function markLine(p: SnapshotPanel) {
    const data: unknown[] = [];
    if (SHOW.band && p.band) {
      data.push({ yAxis: p.band.upper, lineStyle: { color: '#f59e0b', type: 'dashed', width: 1 } });
      data.push({ yAxis: p.band.lower, lineStyle: { color: '#f59e0b', type: 'dashed', width: 1 } });
    }
    // ISO 8528-5 β_f start band (cyan dotted) — the stopwatch-start band.
    if (SHOW.band && p.start_band) {
      data.push({ yAxis: p.start_band.upper, lineStyle: { color: '#0891b2', type: 'dotted', width: 1.2 } });
      data.push({ yAxis: p.start_band.lower, lineStyle: { color: '#0891b2', type: 'dotted', width: 1.2 } });
    }
    if (SHOW.limit && p.limit) {
      data.push({ yAxis: p.limit.value, lineStyle: { color: '#dc2626', type: 'dashed', width: 1.2 } });
    }
    return data.length ? { silent: true, symbol: 'none', label: { show: false }, data } : undefined;
  }

  function extremeLabel(key: keyof SnapshotData['panels'], p: SnapshotPanel): string {
    const value = p.extreme?.value;
    if (typeof value !== 'number' || !Number.isFinite(value)) return '';
    if (key === 'voltage') return `${value.toFixed(1)} V`;
    if (key === 'frequency') return `${value.toFixed(3)} Hz`;
    return fmt2(value);
  }

  function markPoint(key: keyof SnapshotData['panels'], p: SnapshotPanel) {
    const data: unknown[] = [];
    if (SHOW.intersections && p.exit?.ts != null && p.exit.value != null)
      data.push({ coord: [p.exit.ts, p.exit.value], symbol: 'pin', symbolSize: 28,
        itemStyle: { color: '#ea580c' }, label: { show: false } });
    if (SHOW.intersections && p.recovery?.ts != null && p.recovery.value != null)
      data.push({ coord: [p.recovery.ts, p.recovery.value], symbol: 'pin', symbolSize: 30,
        itemStyle: { color: '#10b981' },
        label: { show: true, formatter: `${(p.recovery.rec_s ?? 0).toFixed(2)}s`, position: 'top',
                 color: '#0f172a', fontSize: 10 } });
    if (SHOW.extreme && p.extreme?.ts != null && p.extreme.value != null)
      data.push({ coord: [p.extreme.ts, p.extreme.value], symbol: 'circle', symbolSize: 9,
        itemStyle: { color: '#dc2626', borderColor: '#ffffff', borderWidth: 1 },
        label: {
          show: true,
          formatter: extremeLabel(key, p),
          position: p.limit?.side === 'lower' ? 'bottom' : 'top',
          distance: 7,
          color: '#dc2626',
          fontSize: 10,
          fontWeight: 700,
          backgroundColor: 'rgba(255,255,255,0.88)',
          borderColor: '#fecaca',
          borderWidth: 1,
          borderRadius: 4,
          padding: [2, 5],
        } });
    return data.length ? { data } : undefined;
  }

  function buildOption(s: SnapshotData) {
    const grid = ORDER.map((_, i) => ({ left: 70, right: 28, top: TOPS[i], height: GRID_H }));
    const xAxis = ORDER.map((_, i) => ({
      type: 'time', gridIndex: i,
      axisLabel: { show: i === ORDER.length - 1, color: '#64748b', fontSize: 10 },
      axisLine: { lineStyle: { color: '#cbd5e1' } },
    }));
    const yAxis = ORDER.map((key, i) => {
      const p = s.panels[key];
      return {
        type: 'value', gridIndex: i, scale: true,
        name: (p.not_recovered ? '⚠ ' : '') + p.label,
        nameTextStyle: { fontSize: 10, color: p.not_recovered ? '#b91c1c' : '#64748b', align: 'left' },
        nameLocation: 'end',
        splitLine: { lineStyle: { color: '#eef2f7' } },
        axisLabel: { color: '#64748b', fontSize: 10 },
      };
    });
    const series = ORDER.map((key, i) => {
      const p = s.panels[key];
      return {
        name: p.label, type: 'line', xAxisIndex: i, yAxisIndex: i,
        showSymbol: false, sampling: 'lttb',
        lineStyle: { width: 1.4, color: p.color }, itemStyle: { color: p.color },
        data: pairs(p),
        markLine: markLine(p), markPoint: markPoint(key, p),
      };
    });
    return {
      animation: false,
      tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => fmt2(v) },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      grid, xAxis, yAxis, series,
    };
  }

  function render() {
    if (chart && snap) chart.setOption(buildOption(snap), true);
  }

  onMount(() => {
    chart = echarts.init(el, undefined, { renderer: 'canvas' });
    render();
    const ro = new ResizeObserver(() => chart?.resize());
    ro.observe(el);
    return () => { ro.disconnect(); chart?.dispose(); };
  });

  $effect(() => { void snap; void show; render(); });
</script>

<div class="snap-wrap">
  {#if hasLegend}
    <div class="legend">
      {#if legend.band}<span class="item"><span class="ln band"></span> Tolerance band</span>{/if}
      {#if legend.startBand}<span class="item"><span class="ln start"></span> ISO β_f start band</span>{/if}
      {#if legend.limit}<span class="item"><span class="ln limit"></span> Max deviation limit</span>{/if}
      {#if legend.exit}<span class="item"><span class="dot exit"></span> Band exit</span>{/if}
      {#if legend.recovery}<span class="item"><span class="dot rec"></span> Recovery</span>{/if}
      {#if legend.extreme}<span class="item"><span class="dot ext"></span> Peak deviation</span>{/if}
    </div>
  {/if}
  <div class="snap" bind:this={el}></div>
</div>

<style>
  .snap-wrap { display: flex; flex-direction: column; gap: 6px; }
  .legend {
    display: flex; flex-wrap: wrap; align-items: center; gap: 16px;
    font-size: 12px; color: var(--text-sub); padding: 2px 4px 0;
  }
  .legend .item { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
  .legend .ln { display: inline-block; width: 20px; height: 0; }
  .legend .ln.band { border-top: 2px dashed #f59e0b; }
  .legend .ln.start { border-top: 2px dotted #0891b2; }
  .legend .ln.limit { border-top: 2px dashed #dc2626; }
  .legend .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; }
  .legend .dot.exit { background: #ea580c; }
  .legend .dot.rec { background: #10b981; }
  .legend .dot.ext { background: #dc2626; box-shadow: 0 0 0 1.5px #fff, 0 0 0 2.5px #fecaca; }
  .snap { width: 100%; height: 720px; }
</style>
