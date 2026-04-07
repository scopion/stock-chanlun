<template>
  <div ref="chartRef" class="sub-chart rsi-chart" />
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import type { KLine } from '../../api/stock'

const props = defineProps<{ klines: KLine[]; zoomStart?: number; zoomEnd?: number }>()

const chartRef = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
const zoomId = `rsi-zoom-${Math.random().toString(36).slice(2)}`

function calcRSI(closes: number[], period = 14) {
  const delta = closes.map((v, i) => i > 0 ? v - closes[i - 1] : 0)
  const gain = delta.map(v => Math.max(0, v))
  const loss = delta.map(v => Math.max(0, -v))

  const avgGain: number[] = []
  const avgLoss: number[] = []
  let sGain = gain.slice(1, period + 1).reduce((a, b) => a + b, 0) / period
  let sLoss = loss.slice(1, period + 1).reduce((a, b) => a + b, 0) / period
  avgGain.push(0, sGain)
  avgLoss.push(0, sLoss)

  for (let i = period + 1; i < closes.length; i++) {
    sGain = (sGain * (period - 1) + gain[i]) / period
    sLoss = (sLoss * (period - 1) + loss[i]) / period
    avgGain.push(sGain)
    avgLoss.push(sLoss)
  }

  return closes.map((_, i) => {
    if (i === 0) return 50
    const rs = avgGain[i] / (avgLoss[i] + 1e-9)
    return 100 - 100 / (1 + rs)
  })
}

function buildOption() {
  if (props.klines.length < 20) return {}
  const closes = props.klines.map(k => k.close)
  const rsi = calcRSI(closes)
  const dates = props.klines.map(k => k.date.slice(0, 10))
  const s = props.zoomStart ?? 70
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
      min: 0, max: 100, scale: false, gridIndex: 0,
      axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: '#21262d', type: 'dashed' } },
      axisLabel: { color: '#7d8590', fontSize: 9 }
    }],
    dataZoom: [
      { id: zoomId, type: 'slider', xAxisIndex: 0, start: s, end: e, show: false }
    ],
    series: [
      {
        name: 'RSI', type: 'line', data: rsi,
        lineStyle: { color: '#bc8cff', width: 1.5 },
        itemStyle: { color: '#bc8cff' },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { type: 'dashed', width: 1 },
          data: [
            { yAxis: 70, lineStyle: { color: '#f85149', opacity: 0.5 }, label: { show: false } },
            { yAxis: 30, lineStyle: { color: '#3fb950', opacity: 0.5 }, label: { show: false } },
            { yAxis: 50, lineStyle: { color: '#484f58', opacity: 0.3 }, label: { show: false } }
          ]
        }
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
.rsi-chart {
  width: 100%;
  height: 100px;
  background: var(--bg-card);
  border-radius: 12px;
  border: 1px solid var(--border);
}
</style>