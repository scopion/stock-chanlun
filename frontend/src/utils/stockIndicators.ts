/**
 * MACD / SKDJ 与副图 MACDChart.vue、SKDJChart.vue 同源算法，供主图标记与多图对齐。
 */
import type { KLine } from '../api/stock'

export function calcEMA(data: number[], period: number): number[] {
  const k = 2 / (period + 1)
  const ema = [data[0]]
  for (let i = 1; i < data.length; i++) {
    ema.push(data[i] * k + ema[i - 1] * (1 - k))
  }
  return ema
}

export function calcMACD(closes: number[]) {
  const ema12 = calcEMA(closes, 12)
  const ema26 = calcEMA(closes, 26)
  const dif = ema12.map((v, i) => v - ema26[i])
  const dea = calcEMA(dif, 9)
  return { dif, dea }
}

/** 通达信风格 SKDJ（与 SKDJChart.vue 一致） */
export function calcSKDJ(
  highs: number[],
  lows: number[],
  closes: number[],
  n = 9,
  smoothN = 3,
  smoothM = 1
) {
  const len = closes.length
  const rsv: (number | null)[] = new Array(len).fill(null)
  for (let i = n - 1; i < len; i++) {
    let ln = Infinity
    let hn = -Infinity
    for (let j = i - n + 1; j <= i; j++) {
      if (lows[j] < ln) ln = lows[j]
      if (highs[j] > hn) hn = highs[j]
    }
    rsv[i] = hn === ln ? 50 : ((closes[i] - ln) / (hn - ln)) * 100
  }

  const sk: (number | null)[] = new Array(len).fill(null)
  let prevSk: number | null = null
  for (let i = 0; i < len; i++) {
    const r = rsv[i]
    if (r == null) continue
    prevSk = prevSk == null ? r : (smoothM * r + (smoothN - smoothM) * prevSk) / smoothN
    sk[i] = prevSk
  }

  const sd: (number | null)[] = new Array(len).fill(null)
  let prevSd: number | null = null
  for (let i = 0; i < len; i++) {
    const s = sk[i]
    if (s == null) continue
    prevSd = prevSd == null ? s : (smoothM * s + (smoothN - smoothM) * prevSd) / smoothN
    sd[i] = prevSd
  }

  return { sk, sd }
}

export function macdGoldCrossIndices(dif: number[], dea: number[]): number[] {
  const crosses: number[] = []
  for (let i = 1; i < dif.length; i++) {
    if (dif[i - 1] <= dea[i - 1] && dif[i] > dea[i]) crosses.push(i)
  }
  return crosses
}

export function skdjGoldCrossIndices(sk: (number | null)[], sd: (number | null)[]): number[] {
  const crosses: number[] = []
  for (let i = 1; i < sk.length; i++) {
    const a = sk[i - 1]
    const b = sk[i]
    const ap = sd[i - 1]
    const bp = sd[i]
    if (a == null || b == null || ap == null || bp == null) continue
    if (a <= ap && b > bp) crosses.push(i)
  }
  return crosses
}

/** 当日 MACD 死叉：DIF 下穿 DEA */
export function macdDeathCrossAt(i: number, dif: number[], dea: number[], eps = 1e-9): boolean {
  if (i < 1) return false
  return dif[i - 1] >= dea[i - 1] - eps && dif[i] < dea[i] - eps
}

/** 当日 SKDJ 死叉：SK 下穿 SD */
export function skdjDeathCrossAt(i: number, sk: (number | null)[], sd: (number | null)[], eps = 1e-9): boolean {
  if (i < 1) return false
  const a = sk[i - 1]
  const b = sk[i]
  const ap = sd[i - 1]
  const bp = sd[i]
  if (a == null || b == null || ap == null || bp == null) return false
  return a >= ap - eps && b < bp - eps
}

function klineNumericSeries(klines: KLine[]) {
  const closes = klines.map(k => Number(k.close))
  const highs = klines.map(k => Number(k.high))
  const lows = klines.map(k => Number(k.low))
  if (!closes.length || closes.some(x => !Number.isFinite(x))) {
    return null
  }
  if (highs.some(x => !Number.isFinite(x)) || lows.some(x => !Number.isFinite(x))) return null
  return { closes, highs, lows }
}

/**
 * MACD 金叉与 SKDJ 金叉在 windowBars 根 K 线内共振；标记在较晚金叉日 hi=max(m,s)。
 * 必须：该日 DIF>DEA 且 SK>SD，且当日不能是任一指标的死叉 K 线。
 * 连续候选合并时保留每段最左一根（避免原先取最右一根落在已拐头/死叉附近误标）。
 * 返回 { indices, macdG, skG } 以便外部诊断（生产可删 debugInfo）。
 */
export function computeDualMacdSkdjMarkerIndices(
  klines: KLine[],
  windowBars: number,
  eps = 1e-9
): { indices: number[]; macdG: number[]; skG: number[]; dates: string[] } {
  const series = klineNumericSeries(klines)
  if (!series || klines.length < 30) return { indices: [], macdG: [], skG: [], dates: [] }

  const { closes, highs, lows } = series
  const { dif, dea } = calcMACD(closes)
  const { sk, sd } = calcSKDJ(highs, lows, closes)
  const macdG = macdGoldCrossIndices(dif, dea)
  const skG = skdjGoldCrossIndices(sk, sd)
  const dates = klines.map(k => k.date.slice(0, 10))

  const bullish = (i: number): boolean => {
    const a = sk[i]
    const b = sd[i]
    if (a == null || b == null) return false
    return dif[i] - dea[i] > eps && a - b > eps
  }

  const raw = new Set<number>()
  const debug = []  // 诊断信息

  for (const m of macdG) {
    for (const s of skG) {
      const hi = Math.max(m, s)
      const lo = Math.min(m, s)
      const dist = hi - lo
      if (dist > windowBars) continue
      const macdDead = macdDeathCrossAt(hi, dif, dea, eps)
      const skdjDead = skdjDeathCrossAt(hi, sk, sd, eps)
      const bull = bullish(hi)
      const shouldMark = !macdDead && !skdjDead && bull
      debug.push({ m, s, hi, dist, macdDead, skdjDead, bull, shouldMark, difAtHi: dif[hi], deaAtHi: dea[hi], skAtHi: sk[hi], sdAtHi: sd[hi] })
      if (shouldMark) raw.add(hi)
    }
  }

  if (debug.length) {
    console.log(
      '%c[MACD+SKDJ 诊断]',
      'color:#ffe066;font-weight:700',
      '\nMACD金叉idx:', macdG.map(i => `${i}(${dates[i]})`).join(', '),
      '\nSKDJ金叉idx:', skG.map(i => `${i}(${dates[i]})`).join(', '),
      '\n配对详情:',
      debug.map(d => {
        const ok = d.shouldMark ? '✅' : '❌'
        const reasons = []
        if (d.macdDead) reasons.push('MACD死叉')
        if (d.skdjDead) reasons.push('SKDJ死叉')
        if (!d.bull) reasons.push('非双多头')
        return `${ok} m=${d.m} s=${d.s} hi=${d.hi}(${dates[d.hi]}) 间距=${d.dist} | ${reasons.length ? reasons.join('+') : '通过'} | DIF=${d.difAtHi?.toFixed(3)} DEA=${d.deaAtHi?.toFixed(3)} SK=${d.skAtHi?.toFixed(1)} SD=${d.sdAtHi?.toFixed(1)}`
      })
    )
  }

  const sorted = [...raw].sort((a, b) => a - b)
  if (sorted.length <= 1) return { indices: sorted, macdG, skG, dates }

  const merged: number[] = []
  let runStart = sorted[0]
  let runEnd = sorted[0]
  for (let k = 1; k < sorted.length; k++) {
    if (sorted[k] - runEnd <= 1) {
      runEnd = sorted[k]
    } else {
      merged.push(runStart)
      runStart = sorted[k]
      runEnd = sorted[k]
    }
  }
  merged.push(runStart)
  return { indices: merged, macdG, skG, dates }
}
