<template>
  <div class="kline-wrap">
    <!-- 主图 + 副图 -->
    <div
      ref="chartRef"
      class="kline-chart"
      @touchstart="onTouchStart"
      @touchmove="onTouchMove"
      @touchend="onTouchEnd"
    />

    <!-- 底部状态栏 -->
    <div v-if="barInfoText" class="bar-info">{{ barInfoText }}</div>

    <!-- 骨架屏（数据加载中） -->
    <div v-if="loading" class="chart-skeleton" aria-label="K线加载中">
      <div class="skel-header">
        <div class="skel-bar short" />
        <div class="skel-bar medium" />
        <div class="skel-bar short" />
      </div>
      <div class="skel-chart-area">
        <div class="skel-candle" style="height:65%;left:4%" />
        <div class="skel-candle" style="height:48%;left:10%" />
        <div class="skel-candle" style="height:72%;left:16%" />
        <div class="skel-candle" style="height:55%;left:22%" />
        <div class="skel-candle" style="height:80%;left:28%" />
        <div class="skel-candle" style="height:60%;left:34%" />
        <div class="skel-candle" style="height:70%;left:40%" />
        <div class="skel-candle" style="height:45%;left:46%" />
        <div class="skel-candle" style="height:75%;left:52%" />
        <div class="skel-candle" style="height:58%;left:58%" />
        <div class="skel-candle" style="height:68%;left:64%" />
        <div class="skel-candle" style="height:52%;left:70%" />
        <div class="skel-candle" style="height:78%;left:76%" />
        <div class="skel-candle" style="height:62%;left:82%" />
        <div class="skel-candle" style="height:55%;left:88%" />
      </div>
      <div class="skel-ma-row">
        <div class="skel-dot ma5" />
        <div class="skel-dot ma10" />
        <div class="skel-dot ma20" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import type { KLine, Bi, XiangSegment, Zhongshu, Signal, AISignal, SupportResistance } from '@/api/stock'
import type { IndicatorConfig } from '@/stores/chanlun'
import { calcMACD, calcSKDJ, calcRSI, computeDualMacdSkdjMarkerIndices } from '@/utils/stockIndicators'
import { simplifySupportResistanceLevels } from '@/utils/chartOverlayUtils'

const LONG_PRESS_DELAY = 400
const SWIPE_THRESHOLD = 50

const props = defineProps<{
  klines: KLine[]
  bis: Bi[]
  zhongshus: Zhongshu[]
  signals: Signal[]
  xiangs?: XiangSegment[]
  aiSignal?: AISignal | null
  supportResistance?: SupportResistance[]
  indicators?: IndicatorConfig
  zoomStart?: number
  zoomEnd?: number
  loading?: boolean
}>()

const emit = defineEmits<{ 'zoomChange': [start: number, end: number] }>()

const chartRef = ref<HTMLDivElement | null>(null)
const barInfoText = ref('')
let chart: echarts.ECharts | null = null
let graphicRaf = 0
let resizeObserver: ResizeObserver | null = null
let longPressTimer: ReturnType<typeof setTimeout> | null = null
let touchStartX = 0
let touchStartY = 0
let lastTouchX = 0
let isScrolling = false
let touchCount = 0

// ── 指标配置 ────────────────────────────────────────────────────────────────
function getIndicators(): Required<IndicatorConfig> {
  return {
    ma5: true, ma20: true, ma10: true,
    bis: true, xiangs: false, zhongshus: true,
    signals: true, aiLines: true, supportResistance: true,
    volume: true, macd: false, rsi: false, skdj: false,
    ...(props.indicators || {})
  }
}

// ── 日期处理 ────────────────────────────────────────────────────────────────
function normDay(s: string): string {
  return s.replace('T', ' ').trim().slice(0, 10)
}

function dateToIdxRobust(d: string, dates: string[]): number {
  const key = normDay(d)
  let i = dates.indexOf(key)
  if (i >= 0) return i
  const t = Date.parse(key.replace(/-/g, '/'))
  if (Number.isNaN(t)) return -1
  let best = -1, bestDiff = Infinity
  for (let j = 0; j < dates.length; j++) {
    const tj = Date.parse(dates[j].replace(/-/g, '/'))
    if (Number.isNaN(tj)) continue
    const diff = Math.abs(tj - t)
    if (diff < bestDiff) { bestDiff = diff; best = j }
  }
  return best
}

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

// ── 均线计算 ────────────────────────────────────────────────────────────────
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

// ── 缓存 ────────────────────────────────────────────────────────────────────
let lastDates: string[] = []
let lastMa5: (number | null)[] = []
let lastMa20: (number | null)[] = []
let lastMa10: (number | null)[] = []

function fmtPrice(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(2)
}

function formatBarLine(idx: number): string {
  if (idx < 0 || idx >= props.klines.length) return ''
  const k = props.klines[idx]
  const d = lastDates[idx] ?? k.date.slice(0, 10)
  return `${d}  开 ${fmtPrice(k.open)}  收 ${fmtPrice(k.close)}  高 ${fmtPrice(k.high)}  低 ${fmtPrice(k.low)}  |  MA5 ${fmtPrice(lastMa5[idx])}  MA10 ${fmtPrice(lastMa10[idx])}  MA20 ${fmtPrice(lastMa20[idx])}`
}

function setBarInfoByIndex(idx: number) {
  if (!props.klines.length) { barInfoText.value = ''; return }
  const i = Math.max(0, Math.min(idx, props.klines.length - 1))
  barInfoText.value = formatBarLine(i)
}

// ── 颜色常量 ────────────────────────────────────────────────────────────────
const UP_COLOR = '#ef4444'
const DOWN_COLOR = '#22c55e'
const GRID_COLOR = 'rgba(255,255,255,0.06)'
const TEXT_COLOR = '#64748b'

// ── pixelAt ─────────────────────────────────────────────────────────────────
function pixelAtIdx(i: number, price: number): [number, number] | null {
  if (i < 0 || i >= lastDates.length || !chart) return null
  try {
    const pt = chart.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [lastDates[i], price]) as unknown
    if (!Array.isArray(pt) || pt.length < 2) return null
    const x = Number(pt[0]), y = Number(pt[1])
    return Number.isFinite(x) && Number.isFinite(y) ? [x, y] : null
  } catch { return null }
}

function getGridBounds(): [number, number] {
  if (!chart || !lastDates.length) return [0, 400]
  const mid = props.klines[Math.floor(props.klines.length / 2)]?.close ?? 1
  try {
    const p0 = chart.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [lastDates[0], mid]) as number[]
    const p1 = chart.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [lastDates[lastDates.length - 1], mid]) as number[]
    if (p0?.[0] != null && p1?.[0] != null) {
      return [Math.min(p0[0], p1[0]), Math.max(p0[0], p1[0])]
    }
  } catch { /* ignore */ }
  return [0, 400]
}

// ── 缠论 Overlay ─────────────────────────────────────────────────────────────
type OverlayData = {
  bis: (Bi & { _s: number; _e: number })[]
  xiangs: (XiangSegment & { _s: number; _e: number })[]
  zhongshus: (Zhongshu & { _s: number; _e: number })[]
  signals: (Signal & { _idx: number })[]
  supportResistance: SupportResistance[]
  dualCrossIndices: number[]
  aiSignal: AISignal | null
  _n: number
}
let overlayCache: OverlayData | null = null

function buildOverlayData(): OverlayData {
  const dates = lastDates
  const n = dates.length
  const ind = getIndicators()
  const refPx = props.klines.length ? props.klines[props.klines.length - 1].close : 1

  const dualCrossIndices =
    props.klines.length >= 30 && ind.macd && ind.skdj
      ? computeDualMacdSkdjMarkerIndices(props.klines, 3).indices
      : []

  return {
    bis: ind.bis ? props.bis.flatMap(b => {
      const r = resolveBarRange(b.start, b.end, n, dates)
      return r ? [{ ...b, _s: r[0], _e: r[1] }] : []
    }) : [],
    xiangs: (ind.xiangs && props.xiangs) ? props.xiangs.flatMap(x => {
      const r = resolveBarRange(x.start, x.end, n, dates)
      return r ? [{ ...x, _s: r[0], _e: r[1] }] : []
    }) : [],
    zhongshus: ind.zhongshus ? props.zhongshus.flatMap(z => {
      const r = resolveBarRange(z.start, z.end, n, dates)
      return r ? [{ ...z, _s: r[0], _e: r[1] }] : []
    }) : [],
    signals: ind.signals ? props.signals.flatMap(s => {
      const ix = dateToIdxRobust(s.datetime, dates)
      return ix >= 0 ? [{ ...s, _idx: ix }] : []
    }) : [],
    supportResistance: ind.supportResistance
      ? simplifySupportResistanceLevels(props.supportResistance || [], refPx)
      : [],
    dualCrossIndices,
    aiSignal: ind.aiLines ? (props.aiSignal ?? null) : null,
    _n: n,
  }
}

function applyGraphicOverlay() {
  if (!chart) return
  const data = overlayCache
  if (!data || data._n <= 0 || !lastDates.length) {
    chart.setOption({ graphic: [] }, { replaceMerge: ['graphic'] })
    return
  }

  const opt = (chart as any).getOption?.()
  const dz0 = opt?.dataZoom?.[0]
  const vStart = dz0?.startValue ?? 0
  const vEnd = dz0?.endValue ?? (lastDates.length - 1)
  const viewS = Math.max(0, Math.min(Number(vStart) || 0, lastDates.length - 1))
  const viewE = Math.max(viewS, Math.min(Number(vEnd) || (lastDates.length - 1), lastDates.length - 1))

  const pixelCache = new Map<string, [number, number] | null>()
  const pixelAtIdxCached = (i: number, price: number): [number, number] | null => {
    const key = `${i}:${price}`
    if (pixelCache.has(key)) return pixelCache.get(key) ?? null
    const pt = pixelAtIdx(i, price)
    pixelCache.set(key, pt)
    return pt
  }

  const children: any[] = []
  const [gridLeft, gridRight] = getGridBounds()

  // ── 中枢 ────────────────────────────────────────────────────────
  for (const zs of data.zhongshus) {
    if (zs._e < viewS || zs._s > viewE) continue
    if (zs._e < zs._s) continue
    const a = pixelAtIdxCached(zs._s, zs.range_high)
    const b = pixelAtIdxCached(zs._e, zs.range_low)
    if (!a || !b) continue
    const xPx1 = Math.min(a[0], b[0])
    const xPx2 = Math.max(a[0], b[0])
    const yPx1 = Math.min(a[1], b[1])
    const yPx2 = Math.max(a[1], b[1])
    children.push({ type: 'rect', x: xPx1, y: yPx1,
      width: Math.max(xPx2 - xPx1, 4), height: Math.max(yPx2 - yPx1, 1),
      style: { fill: 'rgba(188, 140, 255, 0.06)', stroke: 'rgba(188, 140, 255, 0.42)', lineWidth: 1, lineDash: [5, 4] },
      z: 100, silent: true })
    children.push({ type: 'text', style: { text: zs.range_high.toFixed(2), fill: 'rgba(188, 140, 255, 0.8)', fontSize: 9, fontFamily: 'monospace' },
      x: xPx1 + 3, y: yPx1 + 11, z: 101, silent: true })
    children.push({ type: 'text', style: { text: zs.range_low.toFixed(2), fill: 'rgba(188, 140, 255, 0.8)', fontSize: 9, fontFamily: 'monospace' },
      x: xPx1 + 3, y: yPx2 - 2, z: 101, silent: true })
  }

  // ── 笔 ─────────────────────────────────────────────────────────
  for (const bi of data.bis) {
    if (bi._e < viewS || bi._s > viewE) continue
    if (bi._e < bi._s) continue
    const p1 = pixelAtIdxCached(bi._s, bi.direction === 'up' ? bi.low : bi.high)
    const p2 = pixelAtIdxCached(bi._e, bi.direction === 'up' ? bi.high : bi.low)
    if (!p1 || !p2) continue
    const color = bi.direction === 'up' ? UP_COLOR : DOWN_COLOR
    children.push({ type: 'line', shape: { x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1] },
      style: { stroke: color, lineWidth: 1.25, opacity: 0.52 }, z: 102, silent: true })
    children.push({ type: 'circle', shape: { cx: p1[0], cy: p1[1], r: 2 },
      style: { fill: color, stroke: '#06080c', lineWidth: 0.8 }, z: 103, silent: true })
    children.push({ type: 'circle', shape: { cx: p2[0], cy: p2[1], r: 2 },
      style: { fill: color, stroke: '#06080c', lineWidth: 1 }, z: 103, silent: true })
  }

  // ── 线段 ───────────────────────────────────────────────────────
  for (const xiang of data.xiangs) {
    if (xiang._e < viewS || xiang._s > viewE) continue
    if (xiang._e < xiang._s) continue
    const p1 = pixelAtIdxCached(
      xiang._s,
      xiang.direction === 'up' ? xiang.low : xiang.high
    )
    const p2 = pixelAtIdxCached(
      xiang._e,
      xiang.direction === 'up' ? xiang.high : xiang.low
    )
    if (!p1 || !p2) continue
    const color = xiang.direction === 'up' ? '#ffe066' : '#ff9f7f'
    children.push({ type: 'line', shape: { x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1] },
      style: { stroke: color, lineWidth: 2, opacity: 0.38 }, z: 101, silent: true })
  }

  // ── 买卖点 ──────────────────────────────────────────────────────
  const buyColors: Record<string, string> = { '一买': DOWN_COLOR, '二买': '#38bdf8', '三买': '#f59e0b' }
  const sellColors: Record<string, string> = { '一卖': UP_COLOR, '二卖': '#ff7b72', '三卖': '#da3633' }
  for (const sig of data.signals) {
    if (sig._idx < viewS || sig._idx > viewE) continue
    const pt = pixelAtIdxCached(sig._idx, sig.price)
    if (!pt) continue
    const color = buyColors[sig.type] || sellColors[sig.type] || '#f59e0b'
    const isBuy = sig.type.includes('买')
    const r = 7
    children.push({ type: 'circle', shape: { cx: pt[0], cy: pt[1], r },
      style: { fill: color, stroke: '#06080c', lineWidth: 2 }, z: 103, silent: true })
    children.push({ type: 'text', style: { text: sig.type, fill: color, fontSize: 10, fontWeight: 700, textAlign: 'center' },
      x: pt[0], y: pt[1] + (isBuy ? -(r + 12) : r + 12), z: 104, silent: true })
  }

  // ── 支撑阻力线 ──────────────────────────────────────────────────
  for (const lvl of data.supportResistance) {
    const yp = pixelAtIdxCached(viewS, lvl.price)?.[1]
    if (yp == null || !Number.isFinite(yp)) continue
    const isSupport = lvl.type === 'support'
    const color = isSupport ? DOWN_COLOR : UP_COLOR
    const dash = isSupport ? [6, 4] : [8, 4]
    const label = isSupport ? `撑 ${lvl.price.toFixed(2)}` : `阻 ${lvl.price.toFixed(2)}`
    const strength = lvl.strength ?? 0.5
    const lw = 0.55 + strength * 0.45
    children.push({ type: 'line', shape: { x1: gridLeft, y1: yp, x2: gridRight, y2: yp },
      style: { stroke: color, lineWidth: lw, opacity: 0.22 + strength * 0.28, lineDash: dash },
      z: 98, silent: true })
    children.push({ type: 'text', style: { text: label, fill: color, fontSize: 8, opacity: 0.45 + strength * 0.35 },
      x: gridLeft + 4, y: yp - 4, z: 99, silent: true })
  }

  // ── AI 信号线 ──────────────────────────────────────────────────
  if (data.aiSignal) {
    const ai = data.aiSignal
    const entryColor = ai.direction === '买入' ? DOWN_COLOR : UP_COLOR
    const hLine = (price: number, stroke: string, dash: number[], lw: number, label: string) => {
      const yp = pixelAtIdxCached(viewS, price)?.[1]
      if (yp == null) return
      children.push({ type: 'line', shape: { x1: gridLeft, y1: yp, x2: gridRight, y2: yp },
        style: { stroke, lineWidth: lw, opacity: 0.8, lineDash: dash }, z: 99, silent: true })
      children.push({ type: 'text', style: { text: label, fill: stroke, fontSize: 10, fontWeight: 700 },
        x: gridLeft + 6, y: yp - 5, z: 104, silent: true })
    }
    if (ai.entry_price != null) hLine(ai.entry_price, entryColor, [7, 4], 1.5, `入场 ${ai.entry_price.toFixed(2)}`)
    if (ai.stop_loss != null) hLine(ai.stop_loss, UP_COLOR, [3, 3], 1.2, `止损 ${ai.stop_loss.toFixed(2)}`)
    if (ai.take_profit != null) hLine(ai.take_profit, DOWN_COLOR, [3, 3], 1.2, `止盈 ${ai.take_profit.toFixed(2)}`)
  }

  // ── MACD+SKDJ 双金叉标记 ─────────────────────────────────────────
  for (const idx of data.dualCrossIndices) {
    if (idx < viewS || idx > viewE) continue
    const pt = pixelAtIdxCached(idx, props.klines[idx].close)
    if (!pt) continue
    children.push({ type: 'circle', shape: { cx: pt[0], cy: pt[1], r: 5 },
      style: { fill: 'rgba(255,224,102,0.85)', stroke: '#06080c', lineWidth: 1.5 }, z: 105, silent: true })
    children.push({ type: 'text', style: { text: '共振', fill: '#e6c355', fontSize: 8, fontWeight: 600, textAlign: 'center' },
      x: pt[0], y: pt[1] - 9, z: 106, silent: true })
  }

  chart.setOption({
    graphic: [{ id: 'chanlun-overlay', type: 'group', children, z: 100, silent: true }]
  }, { replaceMerge: ['graphic'] })
}

function queueGraphic() {
  if (!chart) return
  cancelAnimationFrame(graphicRaf)
  graphicRaf = requestAnimationFrame(() => {
    graphicRaf = 0
    applyGraphicOverlay()
  })
}

// ── 构建 ECharts Option ───────────────────────────────────────────────────────
function buildOption(chartH: number = 300) {
  const klines = props.klines
  if (!klines.length) return {}

  const dates = klines.map(k => k.date.slice(0, 10))
  const ohlc = klines.map(k => [k.open, k.close, k.low, k.high])
  const closes = klines.map(k => k.close)
  const ind = getIndicators()
  const zoomStart = props.zoomStart ?? 0
  const zoomEnd = props.zoomEnd ?? 100

  lastDates = dates
  lastMa5 = ind.ma5 ? calcMA(closes, 5) : []
  lastMa20 = ind.ma20 ? calcMA(closes, 20) : []
  lastMa10 = ind.ma10 ? calcMA(closes, 10) : []

  // 副图计算
  const macdData = calcMACD(closes)
  const skdjData = calcSKDJ(
    klines.map(k => k.high),
    klines.map(k => k.low),
    closes
  )
  const rsiData = calcRSI(closes)

  // 副图开关
  const subCount = [ind.volume, ind.macd, ind.rsi, ind.skdj].filter(Boolean).length
  const chartHeight = chartH
  const gap = 6
  const subHeight = subCount > 0 ? ((chartHeight * 0.6 - gap) / subCount) : 0
  const mainH = subCount > 0 ? chartHeight * 0.38 : chartHeight

  // grid index: 0 = main, 1..N = sub-charts
  const grids: any[] = []
  const xAxes: any[] = []
  const yAxes: any[] = []
  const seriesList: any[] = []

  // Main grid
  grids.push({ left: 8, right: 8, top: 8, bottom: subCount > 0 ? subCount * subHeight + gap * subCount + 4 : 16 })

  // K线
  seriesList.push({
    name: 'K线', type: 'candlestick', data: ohlc,
    xAxisIndex: 0, yAxisIndex: 0, z: 3,
    itemStyle: { color: UP_COLOR, color0: DOWN_COLOR, borderColor: UP_COLOR, borderColor0: DOWN_COLOR }
  })

  // 均线
  if (ind.ma5) seriesList.push({ name: 'MA5', type: 'line', data: lastMa5, xAxisIndex: 0, yAxisIndex: 0,
    lineStyle: { width: 1, color: '#f0b429' }, symbol: 'none', smooth: false, connectNulls: true, z: 4 })
  if (ind.ma10) seriesList.push({ name: 'MA10', type: 'line', data: lastMa10, xAxisIndex: 0, yAxisIndex: 0,
    lineStyle: { width: 1, color: '#ff8c42' }, symbol: 'none', smooth: false, connectNulls: true, z: 4 })
  if (ind.ma20) seriesList.push({ name: 'MA20', type: 'line', data: lastMa20, xAxisIndex: 0, yAxisIndex: 0,
    lineStyle: { width: 1, color: '#58a6ff' }, symbol: 'none', smooth: false, connectNulls: true, z: 4 })

  // Main xAxis
  xAxes.push({ type: 'category', data: dates, gridIndex: 0, boundaryGap: true,
    axisLine: { lineStyle: { color: GRID_COLOR } },
    axisTick: { show: false },
    axisLabel: { color: TEXT_COLOR, fontSize: 9, show: false },
    splitLine: { show: false } })

  // Main yAxis
  yAxes.push({ scale: true, gridIndex: 0,
    splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)', type: 'dashed' } },
    axisLabel: { color: TEXT_COLOR, fontSize: 9 },
    axisLine: { show: false }, axisTick: { show: false } })

  // 副图：成交量 / MACD / RSI / SKDJ
  let subIdx = 1
  const subDef = [
    { key: 'volume' as const, label: '成交量', color: '#7d8590', calc: (i: number) => ({
      value: klines[i].volume,
      itemStyle: { color: klines[i].close >= klines[i].open ? UP_COLOR + '66' : DOWN_COLOR + '66' }
    }) },
    { key: 'macd' as const, label: 'MACD', color: '#38bdf8', calc: (i: number) => ({
      value: macdData.dif[i],
      itemStyle: { color: macdData.dif[i] >= 0 ? UP_COLOR : DOWN_COLOR }
    }) },
    { key: 'rsi' as const, label: 'RSI', color: '#f59e0b', calc: (i: number) => ({
      value: rsiData.rsi[i] ?? null,
      itemStyle: {}
    }) },
    { key: 'skdj' as const, label: 'SKDJ', color: '#a78bfa', calc: (i: number) => ({
      value: skdjData.sk[i] ?? null,
      itemStyle: {}
    }) },
  ]

  for (const def of subDef) {
    if (!ind[def.key]) continue
    const bottom = subCount * subHeight + (subIdx - 1) * (subHeight + gap) + 4
    grids.push({ left: 8, right: 8, top: mainH + (subIdx - 1) * (subHeight + gap) + gap, height: subHeight, bottom: undefined })

    xAxes.push({ type: 'category', data: dates, gridIndex: subIdx, boundaryGap: true,
      axisLine: { lineStyle: { color: GRID_COLOR } },
      axisTick: { show: false },
      axisLabel: { color: TEXT_COLOR, fontSize: 9, show: subIdx === grids.length - 1 },
      splitLine: { show: false } })

    yAxes.push({ scale: true, gridIndex: subIdx,
      splitLine: { show: false },
      axisLabel: { color: TEXT_COLOR, fontSize: 9, formatter: (v: number) => v.toFixed(0) },
      axisLine: { show: false }, axisTick: { show: false },
      max: def.key === 'volume' || def.key === 'macd' ? undefined : 100,
      min: def.key === 'rsi' || def.key === 'skdj' ? 0 : undefined })

    if (def.key === 'volume') {
      seriesList.push({
        name: '成交量', type: 'bar',
        data: klines.map((_, i) => def.calc(i)),
        xAxisIndex: subIdx, yAxisIndex: subIdx,
        barMaxWidth: 6,
      })
    } else if (def.key === 'macd') {
      seriesList.push({ name: 'MACD', type: 'bar', data: klines.map((_, i) => def.calc(i)),
        xAxisIndex: subIdx, yAxisIndex: subIdx, barMaxWidth: 4 })
      seriesList.push({ name: 'DIF', type: 'line', data: macdData.dif,
        xAxisIndex: subIdx, yAxisIndex: subIdx,
        lineStyle: { width: 1, color: '#38bdf8' }, symbol: 'none', smooth: true, z: 5 })
      seriesList.push({ name: 'DEA', type: 'line', data: macdData.dea,
        xAxisIndex: subIdx, yAxisIndex: subIdx,
        lineStyle: { width: 1, color: '#f59e0b' }, symbol: 'none', smooth: true, z: 5 })
    } else if (def.key === 'rsi') {
      seriesList.push({ name: 'RSI', type: 'line', data: rsiData.rsi,
        xAxisIndex: subIdx, yAxisIndex: subIdx,
        lineStyle: { width: 1.2, color: def.color }, symbol: 'none', smooth: true, z: 5 })
    } else {
      seriesList.push({ name: 'K', type: 'line', data: skdjData.sk,
        xAxisIndex: subIdx, yAxisIndex: subIdx,
        lineStyle: { width: 1.2, color: def.color }, symbol: 'none', smooth: true, z: 5 })
      seriesList.push({ name: 'D', type: 'line', data: skdjData.sd,
        xAxisIndex: subIdx, yAxisIndex: subIdx,
        lineStyle: { width: 1, color: '#f59e0b', type: 'dashed' }, symbol: 'none', smooth: true, z: 5 })
    }

    subIdx++
  }

  return {
    backgroundColor: 'transparent',
    animation: false,
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    dataZoom: [
      { type: 'inside', xAxisIndex: Array.from({ length: grids.length }, (_, i) => i), start: zoomStart, end: zoomEnd },
    ],
    series: seriesList,
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'cross',
        lineStyle: { color: '#484f58' },
        label: { show: true, backgroundColor: '#1a222d', color: '#f0f4f8', fontSize: 11,
          formatter: (p: { axisDimension?: string; value?: unknown }) =>
            p.axisDimension === 'y' && p.value != null ? Number(p.value).toFixed(2) : (p.value != null ? String(p.value) : '')
        } },
      backgroundColor: '#1a222d', borderColor: 'rgba(255,255,255,0.12)',
      textStyle: { color: '#f0f4f8', fontSize: 11 },
      formatter(params: unknown) {
        const arr = Array.isArray(params) ? params : [params]
        if (!arr.length) return ''
        const first = arr[0] as { dataIndex?: number }
        const idx = first?.dataIndex
        if (idx == null || idx < 0 || idx >= klines.length) return ''
        const k = klines[idx]
        const d = dates[idx]
        const pct = ((k.close - k.open) / k.open * 100)
        const pctStr = pct >= 0 ? '+' : ''
        return `<div style="font-family:monospace;font-size:11px;line-height:1.6">
          <div style="color:${TEXT_COLOR};margin-bottom:4px;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:3px">${d}</div>
          <div>开 <b>${fmtPrice(k.open)}</b>  收 <b style="color:${k.close >= k.open ? UP_COLOR : DOWN_COLOR}">${fmtPrice(k.close)}</b></div>
          <div>高 ${fmtPrice(k.high)}  低 ${fmtPrice(k.low)}</div>
          <div style="color:${k.close >= k.open ? UP_COLOR : DOWN_COLOR}">${pctStr}${pct.toFixed(2)}%</div>
          ${ind.ma5 ? `<div><span style="color:#f0b429">MA5</span> ${fmtPrice(lastMa5[idx])}</div>` : ''}
          ${ind.ma10 ? `<div><span style="color:#ff8c42">MA10</span> ${fmtPrice(lastMa10[idx])}</div>` : ''}
          ${ind.ma20 ? `<div><span style="color:#58a6ff">MA20</span> ${fmtPrice(lastMa20[idx])}</div>` : ''}
        </div>`
      },
    }
  }
}

// ── 图表初始化 ─────────────────────────────────────────────────────────────
function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)

  const opt = buildOption(chartRef.value.clientHeight)
  chart.setOption(opt)

  setBarInfoByIndex(props.klines.length - 1)
  overlayCache = buildOverlayData()
  queueGraphic()

  chart.getZr().on('globalout', () => setBarInfoByIndex(props.klines.length - 1))
  chart.on('updateAxisPointer', (ev: unknown) => {
    const e = ev as { axesInfo?: { axisDim?: string; value?: string | number }[] }
    const infos = e?.axesInfo
    if (!infos?.length) return
    const xInfo = infos.find(a => a.axisDim === 'x')
    if (xInfo?.value == null) return
    const key = String(xInfo.value)
    let idx = lastDates.indexOf(key)
    if (idx < 0 && typeof xInfo.value === 'number' && Number.isInteger(xInfo.value)) idx = xInfo.value
    if (idx >= 0 && idx < props.klines.length) setBarInfoByIndex(idx)
  })
  chart.on('dataZoom', () => {
    const dz = (chart as any).getOption()?.dataZoom?.[0]
    if (dz && dz.start != null && dz.end != null) emit('zoomChange', dz.start, dz.end)
    queueGraphic()
  })
  chart.on('finished', () => queueGraphic())
}

function updateChart() {
  if (!chart) { initChart(); return }
  chart.setOption(buildOption(chartRef.value?.clientHeight || 300))
  setBarInfoByIndex(props.klines.length - 1)
  overlayCache = buildOverlayData()
  queueGraphic()
}

function getContainerHeight(): number {
  return chartRef.value?.clientHeight || 300
}

function onResize() {
  chart?.resize()
  queueGraphic()
}

onMounted(() => {
  initChart()
  window.addEventListener('resize', onResize)
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => {
      chart?.resize()
      queueGraphic()
    })
    resizeObserver.observe(chartRef.value)
  }
})

onUnmounted(() => {
  cancelAnimationFrame(graphicRaf)
  resizeObserver?.disconnect()
  if (longPressTimer) clearTimeout(longPressTimer)
  if (chart) {
    chart.dispose()
    chart = null
  }
  window.removeEventListener('resize', onResize)
})

function onTouchStart(e: TouchEvent) {
  if (e.touches.length === 1) {
    touchCount = 1
    touchStartX = e.touches[0].clientX
    touchStartY = e.touches[0].clientY
    lastTouchX = touchStartX
    isScrolling = false
    longPressTimer = setTimeout(() => {
      if (!isScrolling && chart) {
        chart.dispatchAction({ type: 'showTip' })
      }
    }, LONG_PRESS_DELAY)
  } else if (e.touches.length === 2) {
    touchCount = 2
    if (longPressTimer) clearTimeout(longPressTimer)
  }
}

function onTouchMove(e: TouchEvent) {
  if (e.touches.length === 1) {
    const dx = e.touches[0].clientX - touchStartX
    const dy = e.touches[0].clientY - touchStartY
    if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > 10) {
      isScrolling = true
    }
    if (!isScrolling && chart) {
      const step = (touchStartX - e.touches[0].clientX) * 0.05
      if (Math.abs(step) >= 1) {
        chart.dispatchAction({ type: 'dataZoom', start: -step, end: step, dataZoomIndex: 0 })
        touchStartX = e.touches[0].clientX
      }
    }
    lastTouchX = e.touches[0].clientX
  } else if (e.touches.length === 2) {
    if (longPressTimer) clearTimeout(longPressTimer)
  }
}

function onTouchEnd(e: TouchEvent) {
  if (longPressTimer) clearTimeout(longPressTimer)
  longPressTimer = null
  if (e.changedTouches.length === 1 && !isScrolling) {
    const dx = e.changedTouches[0].clientX - touchStartX
    if (Math.abs(dx) < 5 && Math.abs(e.changedTouches[0].clientY - touchStartY) < 5) {
      if (chart) {
        chart.dispatchAction({ type: 'hideTip' })
      }
    }
  }
  touchCount = 0
  isScrolling = false
}

function updateOverlayOnly() {
  queueGraphic()
}

watch(
  () => props.klines,
  updateChart
)

watch(
  () => [props.bis, props.zhongshus, props.signals, props.xiangs, props.aiSignal, props.supportResistance],
  updateOverlayOnly,
  { deep: true }
)

watch(
  () => props.indicators,
  () => {
    if (!chart) return
    chart.setOption(buildOption(), { replaceMerge: ['graphic'] })
    queueGraphic()
  },
  { deep: true }
)
</script>

<style scoped>
.kline-wrap {
  width: 100%;
  height: 100%;
  border-radius: 10px;
  overflow: hidden;
  background: var(--bg-elevated);
  position: relative;
}

.kline-chart {
  width: 100%;
  height: 100%;
}

.bar-info {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 6px 10px 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 1.5;
  color: var(--text-secondary);
  border-top: 1px solid var(--border);
  background: var(--bg-elevated);
  word-break: break-all;
}

.chart-skeleton {
  position: absolute;
  inset: 0;
  padding: 12px 8px 8px;
  background: var(--bg-elevated);
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
}
.skel-header {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-bottom: 4px;
}
.skel-bar {
  height: 14px;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-hover) 50%, var(--bg-card) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}
.skel-bar.short { width: 20%; }
.skel-bar.medium { width: 35%; }
.skel-chart-area {
  flex: 1;
  position: relative;
  border-radius: 6px;
  overflow: hidden;
  background: linear-gradient(90deg, var(--bg-secondary) 25%, var(--bg-hover) 50%, var(--bg-secondary) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite 0.2s;
}
.skel-candle {
  position: absolute;
  width: 5%;
  border-radius: 2px;
  background: var(--bg-hover);
  bottom: 0;
  opacity: 0.5;
}
.skel-ma-row {
  display: flex;
  gap: 12px;
  align-items: center;
  padding-top: 2px;
}
.skel-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-hover) 50%, var(--bg-card) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}
.skel-dot.ma5 { background: linear-gradient(90deg, rgba(239,68,68,0.4) 25%, rgba(239,68,68,0.15) 50%, rgba(239,68,68,0.4) 75%); background-size: 200% 100%; }
.skel-dot.ma20 { background: linear-gradient(90deg, rgba(34,197,94,0.4) 25%, rgba(34,197,94,0.15) 50%, rgba(34,197,94,0.4) 75%); background-size: 200% 100%; }
.skel-dot.ma10 { background: linear-gradient(90deg, rgba(56,189,248,0.4) 25%, rgba(56,189,248,0.15) 50%, rgba(56,189,248,0.4) 75%); background-size: 200% 100%; }

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>
