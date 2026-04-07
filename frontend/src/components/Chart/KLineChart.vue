<template>
  <div class="kline-wrap">
    <div ref="chartRef" class="kline-chart" />
    <div v-if="barInfoText" class="bar-info">{{ barInfoText }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import type { KLine, Bi, Zhongshu, Signal, AISignal, SupportResistance } from '../../api/stock'
import type { IndicatorConfig } from '../../stores/chanlun'
import { computeDualMacdSkdjMarkerIndices } from '../../utils/stockIndicators'

const props = defineProps<{
  klines: KLine[]
  bis: Bi[]
  zhongshus: Zhongshu[]
  signals: Signal[]
  xiangs?: { id: string; start: string; end: string; direction: 'up' | 'down'; high: number; low: number }[]
  aiSignal?: AISignal | null
  supportResistance?: SupportResistance[]
  indicators?: IndicatorConfig
}>()

const chartRef = ref<HTMLDivElement | null>(null)
const barInfoText = ref('')
let chart: echarts.ECharts | null = null

/** 获取指标配置，如果未提供则默认全部显示 */
function getIndicators(): Required<IndicatorConfig> {
  return {
    ma5: true, ma20: true, ma60: true,
    bis: true, xiangs: true, zhongshus: true, signals: true, aiLines: true,
    supportResistance: true,
    volume: true, macd: true, rsi: true, skdj: true,
    ...(props.indicators || {})
  }
}

/** buildOption 写入、renderItem 读取 —— ECharts 对 data 里的大对象不可靠，必须走闭包缓存 */
type ChanlunOverlayPayload = {
  bis: any[]
  xiangs: any[]
  zhongshus: any[]
  signals: any[]
  aiSignal: AISignal | null | undefined
  supportResistance: any[]
  _n: number
}
let chanlunOverlayCache: ChanlunOverlayPayload | null = null

const emit = defineEmits<{
  zoomChange: [start: number, end: number]
}>()

/** 统一成 YYYY-MM-DD */
function normDay(s: string): string {
  return s.replace('T', ' ').trim().slice(0, 10)
}

/** 在 dates（YYYY-MM-DD）里找索引；找不到则找时间最接近的一根，避免缠论与 K 线接口行数不一致时全 -1 */
function dateToIdxRobust(d: string, dates: string[]): number {
  const key = normDay(d)
  let i = dates.indexOf(key)
  if (i >= 0) return i
  const t = Date.parse(key.replace(/-/g, '/'))
  if (Number.isNaN(t)) return -1
  let best = -1
  let bestDiff = Infinity
  for (let j = 0; j < dates.length; j++) {
    const tj = Date.parse(dates[j].replace(/-/g, '/'))
    if (Number.isNaN(tj)) continue
    const diff = Math.abs(tj - t)
    if (diff < bestDiff) {
      bestDiff = diff
      best = j
    }
  }
  return best
}

/** 将笔/中枢的起止日期映射到当前 K 线窗口内的下标；两端都无效则返回 null */
function resolveBarRange(start: string, end: string, n: number, dates: string[]): [number, number] | null {
  if (n <= 0) return null
  let s = dateToIdxRobust(start, dates)
  let e = dateToIdxRobust(end, dates)
  if (s < 0 && e < 0) return null
  if (s < 0) s = 0
  if (e < 0) e = n - 1
  if (s > e) [s, e] = [e, s]
  s = Math.max(0, Math.min(n - 1, s))
  e = Math.max(0, Math.min(n - 1, e))
  if (s > e) return null
  return [s, e]
}

function calcMA(closes: number[], period: number): (number | null)[] {
  const out: (number | null)[] = []
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) { out.push(null); continue }
    let s = 0
    for (let j = 0; j < period; j++) s += closes[i - j]
    out.push(s / period)
  }
  return out
}

function fmtPrice(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(2)
}

let lastDates: string[] = []
let lastMa5: (number | null)[] = []
let lastMa20: (number | null)[] = []
let lastMa60: (number | null)[] = []

function formatBarLine(idx: number): string {
  if (idx < 0 || idx >= props.klines.length) return ''
  const k = props.klines[idx]
  const d = lastDates[idx] ?? k.date.slice(0, 10)
  return `${d}  开盘 ${fmtPrice(k.open)}  收盘 ${fmtPrice(k.close)}  最高 ${fmtPrice(k.high)}  最低 ${fmtPrice(k.low)}  |  MA5 ${fmtPrice(lastMa5[idx])}  MA20 ${fmtPrice(lastMa20[idx])}  MA60 ${fmtPrice(lastMa60[idx])}`
}

function setBarInfoByIndex(idx: number) {
  if (!props.klines.length) { barInfoText.value = ''; return }
  const i = Math.max(0, Math.min(idx, props.klines.length - 1))
  barInfoText.value = formatBarLine(i)
}

function buildOption() {
  const dates = props.klines.map(k => k.date.slice(0, 10))
  const ohlc = props.klines.map(k => [k.open, k.close, k.low, k.high])
  const closes = props.klines.map(k => k.close)
  const ind = getIndicators()
  const ma5 = ind.ma5 ? calcMA(closes, 5) : []
  const ma20 = ind.ma20 ? calcMA(closes, 20) : []
  const ma60 = ind.ma60 ? calcMA(closes, 60) : []

  lastDates = dates; lastMa5 = ma5; lastMa20 = ma20; lastMa60 = ma60

  // 预处理缠论数据，提前计算 bar 下标（修复 date 对不齐时 _e=-1 导致整段被跳过）
  const nBar = dates.length
  const overlayData: ChanlunOverlayPayload = {
    bis: ind.bis ? props.bis.flatMap(b => {
      const r = resolveBarRange(b.start, b.end, nBar, dates)
      if (!r) return []
      return [{ ...b, _s: r[0], _e: r[1] }]
    }) : [],
    xiangs: (ind.xiangs && props.xiangs) ? props.xiangs.flatMap(x => {
      const r = resolveBarRange(x.start, x.end, nBar, dates)
      if (!r) return []
      return [{ ...x, _s: r[0], _e: r[1] }]
    }) : [],
    zhongshus: ind.zhongshus ? props.zhongshus.flatMap(z => {
      const r = resolveBarRange(z.start, z.end, nBar, dates)
      if (!r) return []
      return [{ ...z, _s: r[0], _e: r[1] }]
    }) : [],
    signals: ind.signals ? props.signals.flatMap(s => {
      const ix = dateToIdxRobust(s.datetime, dates)
      if (ix < 0) return []
      return [{ ...s, _idx: ix }]
    }) : [],
    aiSignal: ind.aiLines ? props.aiSignal : null,
    supportResistance: ind.supportResistance ? (props.supportResistance || []) : [],
    _n: nBar
  }
  chanlunOverlayCache = overlayData

  const lineSeriesOpts = {
    type: 'line' as const, xAxisIndex: 0, yAxisIndex: 0,
    smooth: true, showSymbol: false, connectNulls: false, z: 4
  }

  const legendData = ['K线']
  const seriesList: any[] = [
    {
      name: 'K线', type: 'candlestick', data: ohlc,
      xAxisIndex: 0, yAxisIndex: 0, z: 3,
      itemStyle: {
        color: '#f85149', color0: '#3fb950',
        borderColor: '#f85149', borderColor0: '#3fb950'
      }
    }
  ]
  if (ind.ma5) { legendData.push('MA5'); seriesList.push({ name: 'MA5', ...lineSeriesOpts, data: ma5, lineStyle: { width: 1.2, color: '#f0b429' }, emphasis: { disabled: true } }) }
  if (ind.ma20) { legendData.push('MA20'); seriesList.push({ name: 'MA20', ...lineSeriesOpts, data: ma20, lineStyle: { width: 1.2, color: '#58a6ff' }, emphasis: { disabled: true } }) }
  if (ind.ma60) { legendData.push('MA60'); seriesList.push({ name: 'MA60', ...lineSeriesOpts, data: ma60, lineStyle: { width: 1.2, color: '#bc8cff' }, emphasis: { disabled: true } }) }

  return {
    animation: false,
    legend: {
      data: legendData,
      top: 2, left: 'center',
      textStyle: { color: '#7d8590', fontSize: 11 },
      itemWidth: 14, itemHeight: 8
    },
    grid: [{ left: 10, right: 10, top: 36, bottom: 40 }],
    xAxis: [{
      type: 'category', data: dates, boundaryGap: true,
      axisLine: { lineStyle: { color: '#30363d' } },
      axisTick: { show: false },
      axisLabel: { color: '#7d8590', fontSize: 10, interval: 'auto' as const },
      splitLine: { show: false }
    }],
    yAxis: [{
      scale: true, gridIndex: 0,
      axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: '#21262d', type: 'dashed' } },
      axisLabel: { color: '#7d8590', fontSize: 10 },
      axisPointer: { label: { show: true, color: '#e6edf3', backgroundColor: '#30363d' } }
    }],
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, start: 70, end: 100 },
      { type: 'slider', xAxisIndex: 0, start: 70, end: 100, height: 20, bottom: 5,
        borderColor: '#30363d', fillerColor: 'rgba(88,166,255,0.1)',
        handleStyle: { color: '#58a6ff' }, textStyle: { color: '#7d8590' }
      }
    ],
    series: seriesList,
    tooltip: {
      trigger: 'axis', axisPointer: {
        type: 'cross',
        lineStyle: { color: '#484f58' },
        label: {
          show: true, backgroundColor: '#30363d', color: '#e6edf3',
          formatter: (p: { axisDimension?: string; value?: unknown }) => {
            if (p.axisDimension === 'y' && p.value != null) return Number(p.value).toFixed(2)
            return p.value != null ? String(p.value) : ''
          }
        }
      },
      backgroundColor: '#1c2128', borderColor: '#30363d',
      textStyle: { color: '#e6edf3', fontSize: 12 },
      formatter: (params: unknown) => {
        const arr = Array.isArray(params) ? params : [params]
        if (!arr.length) return ''
        const first = arr[0] as { dataIndex?: number }
        const idx = first.dataIndex
        if (idx == null || idx < 0 || idx >= props.klines.length) return ''
        const k = props.klines[idx]
        const d = dates[idx]
        let html = `<div style="font-weight:600;margin-bottom:6px;border-bottom:1px solid #30363d;padding-bottom:4px">${d}</div>`
        html += `<div>开盘 <b>${fmtPrice(k.open)}</b></div>`
        html += `<div>收盘 <b>${fmtPrice(k.close)}</b></div>`
        html += `<div>最高 ${fmtPrice(k.high)}　最低 ${fmtPrice(k.low)}</div>`
        html += `<div style="margin-top:6px;padding-top:4px;border-top:1px solid #30363d">`
        html += `<span style="color:#f0b429">■</span> MA5 ${fmtPrice(ma5[idx])}<br/>`
        html += `<span style="color:#58a6ff">■</span> MA20 ${fmtPrice(ma20[idx])}<br/>`
        html += `<span style="color:#bc8cff">■</span> MA60 ${fmtPrice(ma60[idx])}`
        html += `</div>`
        return html
      }
    }
  }
}

/** 用 graphic + convertToPixel 画缠论（custom series 在部分环境下不渲染） */
let graphicRaf = 0

function pixelAt(dateStr: string, price: number): [number, number] | null {
  if (!chart) return null
  try {
    const pt = chart.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [dateStr, price]) as unknown
    if (!Array.isArray(pt) || pt.length < 2) return null
    const x = Number(pt[0])
    const y = Number(pt[1])
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null
    return [x, y]
  } catch {
    return null
  }
}

function pixelAtIdx(i: number, price: number): [number, number] | null {
  if (i < 0 || i >= lastDates.length) return null
  return pixelAt(lastDates[i], price)
}

function applyChanlunGraphic() {
  if (!chart) return
  const data = chanlunOverlayCache
  if (!data || data._n <= 0 || !lastDates.length) {
    chart.setOption({ graphic: [] }, { replaceMerge: ['graphic'] })
    return
  }

  const { bis, xiangs, zhongshus, signals, aiSignal, supportResistance } = data
  const children: any[] = []
  const finder = { xAxisIndex: 0, yAxisIndex: 0 } as const

  let gridLeft = 0
  let gridRight = 800
  try {
    const mid = props.klines[Math.floor(props.klines.length / 2)]?.close ?? 1
    const p0 = chart.convertToPixel(finder, [lastDates[0], mid]) as number[]
    const p1 = chart.convertToPixel(finder, [lastDates[lastDates.length - 1], mid]) as number[]
    if (p0?.length >= 1 && p1?.length >= 1 && Number.isFinite(p0[0]) && Number.isFinite(p1[0])) {
      gridLeft = Math.min(p0[0], p1[0])
      gridRight = Math.max(p0[0], p1[0])
    }
  } catch { /* ignore */ }

  // ── 中枢 ───────────────────────────────────────
  for (const zs of zhongshus) {
    if (zs._e < zs._s) continue
    const a = pixelAtIdx(zs._s, zs.range_high)
    const b = pixelAtIdx(zs._e, zs.range_low)
    if (!a || !b) continue
    const xPx1 = Math.min(a[0], b[0])
    const xPx2 = Math.max(a[0], b[0])
    const yPx1 = Math.min(a[1], b[1])
    const yPx2 = Math.max(a[1], b[1])
    children.push({
      type: 'rect',
      x: xPx1, y: yPx1,
      width: Math.max(xPx2 - xPx1, 4),
      height: Math.max(yPx2 - yPx1, 1),
      style: {
        fill: 'rgba(188, 140, 255, 0.10)',
        stroke: 'rgba(188, 140, 255, 0.60)',
        lineWidth: 1.5,
        lineDash: [5, 4]
      },
      z: 100,
      silent: true
    })
    children.push({
      type: 'text',
      style: { text: zs.range_high.toFixed(2), fill: 'rgba(188, 140, 255, 0.85)', fontSize: 9, fontFamily: 'Noto Sans SC' },
      x: xPx1 + 3, y: yPx1 + 12,
      z: 101,
      silent: true
    })
    children.push({
      type: 'text',
      style: { text: zs.range_low.toFixed(2), fill: 'rgba(188, 140, 255, 0.85)', fontSize: 9, fontFamily: 'Noto Sans SC' },
      x: xPx1 + 3, y: yPx2 - 2,
      z: 101,
      silent: true
    })
  }

  // ── 笔 ─────────────────────────────────────────
  for (const bi of bis) {
    if (bi._e < bi._s) continue
    const p1 = pixelAtIdx(bi._s, bi.direction === 'up' ? bi.low : bi.high)
    const p2 = pixelAtIdx(bi._e, bi.direction === 'up' ? bi.high : bi.low)
    if (!p1 || !p2) continue
    const color = bi.direction === 'up' ? '#f85149' : '#3fb950'
    children.push({
      type: 'line',
      shape: { x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1] },
      style: { stroke: color, lineWidth: 2.5, opacity: 0.9 },
      z: 102,
      silent: true
    })
  }

  // ── 线段 ───────────────────────────────────────
  for (const xiang of xiangs) {
    if (xiang._e < xiang._s) continue
    const p1 = pixelAtIdx(xiang._s, xiang.high)
    const p2 = pixelAtIdx(xiang._e, xiang.low)
    if (!p1 || !p2) continue
    const color = xiang.direction === 'up' ? '#ffe066' : '#ff9f7f'
    children.push({
      type: 'line',
      shape: { x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1] },
      style: { stroke: color, lineWidth: 4, opacity: 0.6 },
      z: 101,
      silent: true
    })
  }

  const buyColors: Record<string, string> = { '一买': '#3fb950', '二买': '#58a6ff', '三买': '#d29922' }
  const sellColors: Record<string, string> = { '一卖': '#f85149', '二卖': '#ff7b72', '三卖': '#da3633' }

  for (const sig of signals) {
    const pt = pixelAtIdx(sig._idx, sig.price)
    if (!pt) continue
    const color = buyColors[sig.type] || sellColors[sig.type] || '#d29922'
    const isBuy = sig.type.includes('买')
    const r = 8
    children.push({
      type: 'circle',
      shape: { cx: pt[0], cy: pt[1], r },
      style: { fill: color, stroke: '#0d1117', lineWidth: 2 },
      z: 103,
      silent: true
    })
    children.push({
      type: 'text',
      style: {
        text: sig.type,
        fill: color,
        fontSize: 11,
        fontWeight: 700,
        fontFamily: 'Noto Sans SC',
        textAlign: 'center'
      },
      x: pt[0],
      y: pt[1] + (isBuy ? -(r + 14) : r + 14),
      z: 104,
      silent: true
    })
  }

  // ── 支撑阻力线 ─────────────────────────────────
  for (const lvl of supportResistance) {
    const yp = pixelAtIdx(0, lvl.price)?.[1]
    if (yp == null || !Number.isFinite(yp)) continue
    const isSupport = lvl.type === 'support'
    const color = isSupport ? '#3fb950' : '#f85149'
    const dash = isSupport ? [6, 4] : [8, 4]
    const label = isSupport ? `撑 ${lvl.price.toFixed(2)}` : `阻 ${lvl.price.toFixed(2)}`
    const strength = lvl.strength ?? 0.5
    const lw = 0.8 + strength * 0.8  // 强度影响线宽

    children.push({
      type: 'line',
      shape: { x1: gridLeft, y1: yp, x2: gridRight, y2: yp },
      style: { stroke: color, lineWidth: lw, opacity: 0.5 + strength * 0.35, lineDash: dash },
      z: 98,
      silent: true
    })
    children.push({
      type: 'text',
      style: {
        text: label,
        fill: color,
        fontSize: 10,
        fontFamily: 'Noto Sans SC',
        opacity: 0.7 + strength * 0.3
      },
      x: gridLeft + 6,
      y: yp - 4,
      z: 99,
      silent: true
    })
  }

  if (aiSignal) {
    const entryColor = aiSignal.direction === '买入' ? '#3fb950' : '#f85149'
    const hLine = (price: number, stroke: string, dash: number[], lw: number) => {
      const yp = pixelAtIdx(0, price)?.[1]
      if (yp == null || !Number.isFinite(yp)) return
      children.push({
        type: 'line',
        shape: { x1: gridLeft, y1: yp, x2: gridRight, y2: yp },
        style: { stroke, lineWidth: lw, opacity: 0.85, lineDash: dash },
        z: 99,
        silent: true
      })
    }
    if (aiSignal.entry_price != null) {
      hLine(aiSignal.entry_price, entryColor, [7, 4], 1.5)
      const yy = pixelAtIdx(0, aiSignal.entry_price)?.[1]
      if (yy != null) {
        children.push({
          type: 'text',
          style: { text: `入场 ${aiSignal.entry_price.toFixed(2)}`, fill: entryColor, fontSize: 11, fontWeight: 700, fontFamily: 'Noto Sans SC' },
          x: gridLeft + 8, y: yy - 6, z: 104, silent: true
        })
      }
    }
    if (aiSignal.stop_loss != null) {
      hLine(aiSignal.stop_loss, '#f85149', [3, 3], 1.2)
      const yy = pixelAtIdx(0, aiSignal.stop_loss)?.[1]
      if (yy != null) {
        children.push({
          type: 'text',
          style: { text: `止损 ${aiSignal.stop_loss.toFixed(2)}`, fill: '#f85149', fontSize: 11, fontWeight: 700, fontFamily: 'Noto Sans SC' },
          x: gridLeft + 8, y: yy + 14, z: 104, silent: true
        })
      }
    }
    if (aiSignal.take_profit != null) {
      hLine(aiSignal.take_profit, '#3fb950', [3, 3], 1.2)
      const yy = pixelAtIdx(0, aiSignal.take_profit)?.[1]
      if (yy != null) {
        children.push({
          type: 'text',
          style: { text: `止盈 ${aiSignal.take_profit.toFixed(2)}`, fill: '#3fb950', fontSize: 11, fontWeight: 700, fontFamily: 'Noto Sans SC' },
          x: gridLeft + 8, y: yy - 6, z: 104, silent: true
        })
      }
    }
  }

  // ── MACD + SKDJ 双金叉（算法与副图 utils/stockIndicators 同源；合并段取最左一根防误标死叉日） ──
  if (props.klines.length >= 30) {
    const RESONANCE_WINDOW = 3
    const { indices: markIdxs } = computeDualMacdSkdjMarkerIndices(props.klines, RESONANCE_WINDOW)
    for (const idx of markIdxs) {
      const pt = pixelAtIdx(idx, props.klines[idx].close)
      if (!pt) {
        console.warn(`[MACD+SKDJ] pixelAtIdx 返回 null，idx=${idx}`)
        continue
      }
      console.log(`[MACD+SKDJ 标记] idx=${idx} 日期=${props.klines[idx].date.slice(0,10)} 像素=(${pt[0].toFixed(1)},${pt[1].toFixed(1)}) 收盘=${props.klines[idx].close}`)
      children.push({
        type: 'circle',
        shape: { cx: pt[0], cy: pt[1], r: 7 },
        style: { fill: '#ffe066', stroke: '#0d1117', lineWidth: 2.5 },
        z: 106, silent: true
      })
      children.push({
        type: 'text',
        style: {
          text: 'MACD+SKDJ',
          fill: '#ffe066',
          fontSize: 10, fontWeight: 700,
          fontFamily: 'Noto Sans SC',
          textAlign: 'center'
        },
        x: pt[0],
        y: pt[1] - 12,
        z: 107, silent: true
      })
    }
  }

  chart.setOption({
    graphic: [{ id: 'chanlun-overlay', type: 'group', children, z: 100, silent: true }]
  }, { replaceMerge: ['graphic'] })
}

function queueChanlunGraphic() {
  if (!chart) return
  cancelAnimationFrame(graphicRaf)
  graphicRaf = requestAnimationFrame(() => {
    graphicRaf = 0
    applyChanlunGraphic()
  })
}

function onChartFinished() {
  queueChanlunGraphic()
}

function onChartDataZoom() {
  queueChanlunGraphic()
  const dz = (chart as any).getOption()?.dataZoom?.[0]
  if (dz && dz.start != null && dz.end != null) {
    emit('zoomChange', dz.start, dz.end)
  }
}

function onAxisPointerUpdate(ev: unknown) {
  const e = ev as { axesInfo?: { axisDim?: string; value?: string | number }[] }
  const infos = e?.axesInfo
  if (!infos?.length) return
  const xInfo = infos.find(a => a.axisDim === 'x')
  if (xInfo?.value == null) return
  const key = String(xInfo.value)
  let idx = lastDates.indexOf(key)
  if (idx < 0 && typeof xInfo.value === 'number' && Number.isInteger(xInfo.value)) idx = xInfo.value
  if (idx >= 0 && idx < props.klines.length) setBarInfoByIndex(idx)
}

function onChartGlobalOut() {
  setBarInfoByIndex(props.klines.length - 1)
}

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)
  chart.setOption(buildOption())
  setBarInfoByIndex(props.klines.length - 1)
  chart.getZr().on('globalout', onChartGlobalOut)
  chart.on('updateAxisPointer', onAxisPointerUpdate)
  chart.on('finished', onChartFinished)
  chart.on('dataZoom', onChartDataZoom)
  queueChanlunGraphic()
}

function updateChart() {
  if (!chart) return
  chart.setOption(buildOption())
  setBarInfoByIndex(props.klines.length - 1)
  queueChanlunGraphic()
}

function onResize() {
  chart?.resize()
  queueChanlunGraphic()
}

onMounted(() => {
  initChart()
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  cancelAnimationFrame(graphicRaf)
  graphicRaf = 0
  if (chart) {
    chart.off('updateAxisPointer', onAxisPointerUpdate)
    chart.off('finished', onChartFinished)
    chart.off('dataZoom', onChartDataZoom)
    chart.getZr().off('globalout', onChartGlobalOut)
    chart.dispose()
    chart = null
  }
  window.removeEventListener('resize', onResize)
})

watch(
  () => [props.klines, props.bis, props.zhongshus, props.signals, props.xiangs, props.aiSignal, props.supportResistance, props.indicators],
  updateChart, { deep: true }
)
</script>

<style scoped>
.kline-wrap {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  background: var(--bg-card);
}
.kline-chart { width: 100%; height: 420px; }
.bar-info {
  padding: 8px 12px 10px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary, #7d8590);
  border-top: 1px solid var(--border);
  font-variant-numeric: tabular-nums;
  word-break: break-all;
}
</style>
