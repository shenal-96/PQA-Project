<script lang="ts">
  import { onMount } from 'svelte';
  import * as echarts from 'echarts';
  import type { MetricSeries } from '../backend/types';

  let { series, label, color = '#2563eb' }:
    { series: MetricSeries; label: string; color?: string } = $props();

  let el: HTMLDivElement;
  let chart: echarts.ECharts | undefined;

  function render() {
    if (!chart || !series) return;
    chart.setOption(
      {
        grid: { left: 60, right: 24, top: 28, bottom: 56 },
        tooltip: { trigger: 'axis' },
        xAxis: {
          type: 'time',
          axisLine: { lineStyle: { color: '#cbd5e1' } },
          axisLabel: { color: '#64748b' },
        },
        yAxis: {
          type: 'value',
          scale: true,
          splitLine: { lineStyle: { color: '#e2e8f0' } },
          axisLabel: { color: '#64748b' },
        },
        dataZoom: [
          { type: 'inside' },
          { type: 'slider', height: 18, bottom: 12 },
        ],
        series: [
          {
            name: label,
            type: 'line',
            showSymbol: false,
            sampling: 'lttb',
            lineStyle: { width: 1.6, color },
            itemStyle: { color },
            data: series.timestamps.map((t, i) => [t, series.values[i]]),
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
    return () => {
      ro.disconnect();
      chart?.dispose();
    };
  });

  // Re-render whenever the selected series / label / colour changes.
  $effect(() => {
    void series;
    void label;
    void color;
    render();
  });
</script>

<div class="chart" bind:this={el}></div>

<style>
  .chart {
    width: 100%;
    height: 400px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 6px;
  }
</style>
