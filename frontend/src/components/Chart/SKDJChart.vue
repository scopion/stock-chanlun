<template>
  <div ref="chartRef" class="sub-chart skdj-chart" />
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import type { KLine } from '../../api/stock'
import { calcSKDJ } from '../../utils/stockIndicators'

const props = defineProps<{ klines: KLine[] }>()

const chartRef = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function buildOption() {
  if (props.klines.length < 12) return {}
  const highs = props.klines.map(k => Number(k.high))
  const lows = props.klines.map(k => Number(k.low))
  const closes = props.klines.map(k => Number(k.close))
  const { sk, sd } = calcSKDJ(highs, lows, closes)
  const dates = props.klines.map(k => k.date.slice(0, 10))

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
    series: [
      {
        name: 'SK',
        type: 'line',
        data: sk,
        connectNulls: false,
        showSymbol: false,
        lineStyle: { color: '#58a6ff', width: 1.2 },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { type: 'dashed', width: 1 },
          data: [
            { yAxis: 80, lineStyle: { color: '#f85149', opacity: 0.45 }, label: { show: false } },
            { yAxis: 20, lineStyle: { color: '#3fb950', opacity: 0.45 }, label: { show: false } },
            { yAxis: 50, lineStyle: { color: '#484f58', opacity: 0.25 }, label: { show: false } }
          ]
        }
      },
      {
        name: 'SD',
        type: 'line',
        data: sd,
        connectNulls: false,
        showSymbol: false,
        lineStyle: { color: '#d29922', width: 1.2 }
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

watch(() => props.klines, () => {
  if (!chart) return
  chart.setOption(buildOption(), { notMerge: true })
}, { deep: true })
</script>

<style scoped>
.skdj-chart {
  width: 100%;
  height: 100px;
  background: var(--bg-card);
  border-radius: 12px;
  border: 1px solid var(--border);
}
</style>
