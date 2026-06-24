<script lang="ts">
  import { onMount } from 'svelte';
  import * as echarts from 'echarts';
  import type { MetricSeries } from '../backend/types';
  import { fmt2 } from './format';

  let { series, label, color = '#2563eb', band, windows }:
    {
      series: MetricSeries;
      label: string;
      color?: string;
      // Optional ISO 8528-5 δ band (steady-state) + dwell windows to overlay.
      band?: { lower: number; upper: number };
      windows?: { start: string; end: string }[];
    } = $props();

  const TEAL = '#0d9488';

  let el: HTMLDivElement;
  let chart: echarts.ECharts | undefined;

  function render() {
    if (!chart || !series) return;
    // δ band lines (markLine) + shaded dwell windows (markArea), drawn only when
    // steady-state context is supplied for this metric.
    const markLine = band
      ? {
          symbol: 'none',
          silent: true,
          lineStyle: { color: TEAL, type: 'dashed', width: 1.2 },
          label: { formatter: (p: { value: number }) => fmt2(p.value), color: TEAL, fontSize: 10 },
          data: [{ yAxis: band.upper }, { yAxis: band.lower }],
        }
      : undefined;
    const markArea = windows && windows.length
      ? {
          silent: true,
          itemStyle: { color: 'rgba(13,148,136,0.08)' },
          data: windows.map((w) => [{ xAxis: w.start }, { xAxis: w.end }]),
        }
      : undefined;
    chart.setOption(
      {
        grid: { left: 60, right: 24, top: 28, bottom: 56 },
        tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => fmt2(v) },
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
            ...(markLine ? { markLine } : {}),
            ...(markArea ? { markArea } : {}),
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
    void band;
    void windows;
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
