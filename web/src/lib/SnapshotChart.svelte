<script lang="ts">
  import { onMount } from 'svelte';
  import * as echarts from 'echarts';
  import type { SnapshotData, SnapshotPanel } from '../backend/types';

  let { snap }: { snap: SnapshotData } = $props();

  let el: HTMLDivElement;
  let chart: echarts.ECharts | undefined;

  const ORDER: Array<keyof SnapshotData['panels']> = ['voltage', 'current', 'frequency', 'power'];
  const TOPS = ['4%', '28%', '52%', '76%'];
  const GRID_H = '17%';

  function pairs(p: SnapshotPanel) {
    return p.timestamps.map((t, i) => [t, p.values[i]]);
  }

  function markLine(p: SnapshotPanel) {
    const data: unknown[] = [];
    if (p.band) {
      data.push({ yAxis: p.band.upper, lineStyle: { color: '#f59e0b', type: 'dashed', width: 1 } });
      data.push({ yAxis: p.band.lower, lineStyle: { color: '#f59e0b', type: 'dashed', width: 1 } });
    }
    if (p.limit) {
      data.push({ yAxis: p.limit.value, lineStyle: { color: '#dc2626', type: 'dashed', width: 1.2 } });
    }
    return data.length ? { silent: true, symbol: 'none', label: { show: false }, data } : undefined;
  }

  function markPoint(p: SnapshotPanel) {
    const data: unknown[] = [];
    if (p.exit?.ts != null && p.exit.value != null)
      data.push({ coord: [p.exit.ts, p.exit.value], symbol: 'pin', symbolSize: 28,
        itemStyle: { color: '#ea580c' }, label: { show: false } });
    if (p.recovery?.ts != null && p.recovery.value != null)
      data.push({ coord: [p.recovery.ts, p.recovery.value], symbol: 'pin', symbolSize: 30,
        itemStyle: { color: '#10b981' },
        label: { show: true, formatter: `${(p.recovery.rec_s ?? 0).toFixed(1)}s`, position: 'top',
                 color: '#0f172a', fontSize: 10 } });
    if (p.extreme?.ts != null && p.extreme.value != null)
      data.push({ coord: [p.extreme.ts, p.extreme.value], symbol: 'circle', symbolSize: 9,
        itemStyle: { color: '#dc2626' }, label: { show: false } });
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
        markLine: markLine(p), markPoint: markPoint(p),
      };
    });
    return {
      animation: false,
      tooltip: { trigger: 'axis' },
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

  $effect(() => { void snap; render(); });
</script>

<div class="snap" bind:this={el}></div>

<style>
  .snap { width: 100%; height: 720px; }
</style>
