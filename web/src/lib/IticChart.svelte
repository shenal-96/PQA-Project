<script lang="ts">
  import { onMount } from 'svelte';
  import * as echarts from 'echarts';
  import type { IticData } from '../backend/types';

  let { itic }: { itic: IticData } = $props();

  let el: HTMLDivElement;
  let chart: echarts.ECharts | undefined;

  function render() {
    if (!chart || !itic) return;
    const inside = itic.events.filter((e) => e.inside).map((e) => [e.dur, e.pct]);
    const outside = itic.events.filter((e) => !e.inside).map((e) => [e.dur, e.pct]);
    chart.setOption(
      {
        grid: { left: 64, right: 24, top: 36, bottom: 56 },
        legend: { top: 4, textStyle: { color: '#475569', fontSize: 11 } },
        tooltip: {
          trigger: 'item',
          formatter: (p: { seriesName: string; value: [number, number] }) =>
            Array.isArray(p.value)
              ? `${p.seriesName}<br/>${p.value[0].toFixed(2)} s · ${p.value[1].toFixed(2)} %`
              : p.seriesName,
        },
        xAxis: {
          type: 'log', min: itic.x_min, max: itic.x_max,
          name: 'Event duration (s)', nameLocation: 'middle', nameGap: 32,
          axisLine: { lineStyle: { color: '#cbd5e1' } }, axisLabel: { color: '#64748b' },
          splitLine: { lineStyle: { color: '#eef2f7' } },
        },
        yAxis: {
          type: 'value', min: 0, max: itic.y_max,
          name: 'Voltage (% of nominal)',
          axisLine: { lineStyle: { color: '#cbd5e1' } }, axisLabel: { color: '#64748b' },
          splitLine: { lineStyle: { color: '#e2e8f0' } },
        },
        series: [
          {
            name: 'ITIC upper (overvoltage)', type: 'line', data: itic.upper,
            showSymbol: false, lineStyle: { color: '#dc2626', width: 2 }, itemStyle: { color: '#dc2626' }, z: 2,
          },
          {
            name: 'ITIC lower (undervoltage)', type: 'line', data: itic.lower,
            showSymbol: false, lineStyle: { color: '#2563eb', width: 2 }, itemStyle: { color: '#2563eb' }, z: 2,
            markLine: {
              silent: true, symbol: 'none',
              lineStyle: { color: '#94a3b8', type: 'dotted' }, label: { show: false },
              data: [{ yAxis: 100 }],
            },
          },
          {
            name: `Compliant (${inside.length})`, type: 'scatter', data: inside,
            symbolSize: 11, itemStyle: { color: '#16a34a', borderColor: '#0f172a', borderWidth: 1 }, z: 4,
          },
          {
            name: `ITIC violation (${outside.length})`, type: 'scatter', data: outside,
            symbol: 'diamond', symbolSize: 13,
            itemStyle: { color: '#dc2626', borderColor: '#0f172a', borderWidth: 1 }, z: 5,
          },
        ],
      },
      true,
    );
  }

  onMount(() => {
    chart = echarts.init(el, undefined, { renderer: 'canvas' });
    render();
    const ro = new ResizeObserver(() => chart?.resize());
    ro.observe(el);
    return () => { ro.disconnect(); chart?.dispose(); };
  });

  $effect(() => { void itic; render(); });
</script>

<div class="chart" bind:this={el}></div>
{#if itic && itic.events.length === 0}
  <div class="note">No events with a detected band exit + recovery to plot on the curve.</div>
{/if}

<style>
  .chart { width: 100%; height: 420px; background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 6px; }
  .note { font-size: 12px; color: var(--text-sub); margin-top: 6px; }
</style>
