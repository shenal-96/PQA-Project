<script lang="ts">
  import { onMount } from 'svelte';
  import * as echarts from 'echarts';
  import type { EventOverlayMarker, MetricSeries } from '../backend/types';
  import { fmt2 } from './format';

  let { series, overlay }:
    { series: MetricSeries | undefined; overlay: EventOverlayMarker[] } = $props();

  let el: HTMLDivElement;
  let chart: echarts.ECharts | undefined;

  const AMBER = '#f59e0b';
  const BLUE = '#2563eb';

  function render() {
    if (!chart) return;
    if (!series) {
      chart.clear();
      return;
    }
    // One vertical marker per detected event, annotated with its signed kW step.
    const markData = overlay
      .filter((m) => m.timestamp != null)
      .map((m) => ({
        xAxis: m.timestamp as string | number,
        label: {
          show: true,
          formatter: m.label,
          color: '#b45309',
          fontSize: 10,
          rotate: 90,
          align: 'left',
          verticalAlign: 'middle',
          position: 'insideEndTop',
        },
      }));

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
          name: 'kW',
          splitLine: { lineStyle: { color: '#e2e8f0' } },
          axisLabel: { color: '#64748b' },
        },
        dataZoom: [
          { type: 'inside' },
          { type: 'slider', height: 18, bottom: 12 },
        ],
        series: [
          {
            name: 'Active Power (kW)',
            type: 'line',
            showSymbol: false,
            sampling: 'lttb',
            lineStyle: { width: 1.6, color: BLUE },
            itemStyle: { color: BLUE },
            data: series.timestamps.map((t, i) => [t, series.values[i]]),
            markLine: {
              symbol: 'none',
              silent: true,
              lineStyle: { color: AMBER, type: 'dotted', width: 1.4 },
              data: markData,
            },
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

  $effect(() => {
    void series;
    void overlay;
    render();
  });
</script>

<div class="wrap">
  <div class="legend">
    <span class="dot blue"></span> Active Power (kW)
    <span class="dot amber"></span> Detected event ({overlay.length})
  </div>
  <div class="chart" bind:this={el}></div>
</div>

<style>
  .wrap { display: flex; flex-direction: column; gap: 6px; }
  .legend { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-sub); }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-left: 8px; }
  .dot.blue { background: #2563eb; }
  .dot.amber { background: #f59e0b; }
  .chart {
    width: 100%;
    height: 400px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 6px;
  }
</style>
