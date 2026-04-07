<template>
  <div ref="chartRef" class="sub-chart macd-chart" />
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import type { KLine } from '../../api/stock'
import { calcMACD } from '../../utils/stockIndicators'

const props = defineProps<{ klines: KLine[]; zoomStart?: number; zoomEnd?: number }>()

const chartRef = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

const zoomId = `macd-zoom-${Math.random().toString(36).slice(2)}`

function buildOption() {
  if (props.klines.length < 30) return {}
  const closes = props.klines.map(k => Number(k.close))
  const { dif, dea } = calcMACD(closes)
  const bar = dif.map((v, i) => (v - dea[i]) * 2)
  const dates = props.klines.map(k => k.date.slice(0, 10))
  const s = props.zoomStart ?? 0
  const e = props.zoomEnd ?? 100

  return {
    animation: false,
    grid: { left: 10, right: 10, top: 10, bottom: 30 },
    xAxis: [{
      type: 'category', data: dates,
      axisLine: { lineStyle: { color: '#30363d' } },
      axisTick: { show: false }, axisLabel: { show: false }, splitLine: { show: false }
    }],
    yAxis: [{
      scale: true, gridIndex: 0,
      axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: '#21262d', type: 'dashed' } },
      axisLabel: { color: '#7d8590', fontSize: 9 }
    }],
    dataZoom: [
      { id: zoomId, type: 'slider', xAxisIndex: 0, start: s, end: e, show: false }
    ],
    series: [
      { name: 'DIF', type: 'line', data: dif, lineStyle: { color: '#58a6ff', width: 1 } },
      { name: 'DEA', type: 'line', data: dea, lineStyle: { color: '#d29922', width: 1 } },
      {
        name: 'MACD', type: 'bar', data: bar.map(v => v >= 0 ? v : 0),
        itemStyle: { color: '#f85149' }, barMaxWidth: 4
      },
      {
        name: 'MACDneg', type: 'bar', data: bar.map(v => v < 0 ? Math.abs(v) : 0),
        itemStyle: { color: '#3fb950' }, barMaxWidth: 4
      }
    ],
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1c2128', borderColor: '#30363d',
      textStyle: { color: '#e6edf3', fontSize: 11 }
    }
  }
}

onMounted(() => {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)
  chart.setOption(buildOption())
  window.addEventListener('resize', () => chart?.resize())
})
onUnmounted(() => { chart?.dispose() })

watch([() => props.klines, () => props.zoomStart, () => props.zoomEnd], () => {
  if (!chart) return
  chart.setOption(buildOption(), { notMerge: true })
}, { deep: true })
</script>

<style scoped>
.macd-chart {
  width: 100%;
  height: 120px;
  background: var(--bg-card);
  border-radius: 12px;
  border: 1px solid var(--border);
}
</style>
