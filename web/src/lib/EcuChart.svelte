<script lang="ts">
  import { onMount } from 'svelte';
  import * as echarts from 'echarts';

  export interface EcuSeries {
    name: string;
    label: string;
    values: Array<number | null>;
  }

  let { timestamps, series }: { timestamps: Array<string | number>; series: EcuSeries[] } = $props();

  // Distinct, colour-blind-friendly-ish palette cycled across channels.
  const PALETTE = [
    '#2563eb', '#dc2626', '#16a34a', '#ea580c', '#9333ea',
    '#0891b2', '#f59e0b', '#10b981', '#db2777', '#475569',
  ];

  let el: HTMLDivElement;
  let chart: echarts.ECharts | undefined;

  function render() {
    if (!chart) return;
    chart.setOption(
      {
        grid: { left: 60, right: 24, top: 36, bottom: 64 },
        legend: { type: 'scroll', top: 4, textStyle: { color: '#475569', fontSize: 11 } },
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
          { type: 'slider', height: 18, bottom: 16 },
        ],
        series: series.map((s, i) => ({
          name: s.label,
          type: 'line',
          showSymbol: false,
          sampling: 'lttb',
          lineStyle: { width: 1.5, color: PALETTE[i % PALETTE.length] },
          itemStyle: { color: PALETTE[i % PALETTE.length] },
          data: timestamps.map((t, j) => [t, s.values[j]]),
        })),
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
    void timestamps;
    void series;
    render();
  });
</script>

<div class="chart" bind:this={el}></div>

<style>
  .chart {
    width: 100%;
    height: 440px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 6px;
  }
</style>
