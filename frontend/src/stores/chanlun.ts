import { defineStore } from 'pinia'
import { ref } from 'vue'
import { stockApi, type KLine, type ChanlunResult, type AISignal, type SupportResistance } from '../api/stock'

export type LevelOption = '1min' | '5min' | '15min' | '30min' | '60min' | 'daily' | 'weekly' | 'monthly'

/** 指标显示配置 */
export interface IndicatorConfig {
  // 主图
  ma5: boolean
  ma20: boolean
  ma60: boolean
  bis: boolean
  xiangs: boolean
  zhongshus: boolean
  signals: boolean
  aiLines: boolean
  supportResistance: boolean
  // 副图
  volume: boolean
  macd: boolean
  rsi: boolean
  skdj: boolean
}

export const defaultIndicators: IndicatorConfig = {
  ma5: true,
  ma20: true,
  ma60: true,
  bis: true,
  xiangs: true,
  zhongshus: true,
  signals: true,
  aiLines: true,
  supportResistance: true,
  volume: true,
  macd: true,
  rsi: false,
  skdj: false,
}

export const useChanlunStore = defineStore('chanlun', () => {
  const klines = ref<KLine[]>([])
  const chanlunResult = ref<ChanlunResult | null>(null)
  const aiSignal = ref<AISignal | null>(null)
  const loadingKline = ref(false)
  const loadingChanlun = ref(false)
  const loadingAI = ref(false)
  const errorKline = ref<string | null>(null)
  const errorChanlun = ref<string | null>(null)
  const errorAI = ref<string | null>(null)
  const currentLevel = ref<LevelOption>('daily')
  const aiModel = ref<string>('deepseek')
  const indicators = ref<IndicatorConfig>({ ...defaultIndicators })

  async function fetchKline(code: string, level: LevelOption = 'daily') {
    loadingKline.value = true
    errorKline.value = null
    try {
      const res = await stockApi.kline(code, level)
      klines.value = res.data.klines || []
    } catch (e: any) {
      errorKline.value = e.message
    } finally {
      loadingKline.value = false
    }
  }

  async function fetchChanlun(code: string, level: LevelOption = 'daily') {
    loadingChanlun.value = true
    errorChanlun.value = null
    try {
      const res = await stockApi.chanlun(code, level)
      chanlunResult.value = res.data
    } catch (e: any) {
      errorChanlun.value = e.message
    } finally {
      loadingChanlun.value = false
    }
  }

  async function fetchAISignal(code: string, level: LevelOption = 'daily') {
    loadingAI.value = true
    errorAI.value = null
    try {
      const res = await stockApi.aiSignal(code, level, aiModel.value)
      aiSignal.value = res.data
    } catch (e: any) {
      errorAI.value = e.message
    } finally {
      loadingAI.value = false
    }
  }

  async function loadAll(code: string, level: LevelOption = 'daily') {
    currentLevel.value = level
    await Promise.all([
      fetchKline(code, level),
      fetchChanlun(code, level),
      fetchAISignal(code, level),
    ])
  }

  async function setAiModel(model: string) {
    aiModel.value = model
    await stockApi.setAiModel(model)
    const code = ''
    await fetchAISignal(code, currentLevel.value)
  }

  function toggleIndicator(key: keyof IndicatorConfig) {
    indicators.value[key] = !indicators.value[key]
  }

  function setIndicator(key: keyof IndicatorConfig, value: boolean) {
    indicators.value[key] = value
  }

  return {
    klines, chanlunResult, aiSignal,
    loadingKline, loadingChanlun, loadingAI,
    errorKline, errorChanlun, errorAI,
    currentLevel, aiModel, indicators,
    fetchKline, fetchChanlun, fetchAISignal, loadAll, setAiModel,
    toggleIndicator, setIndicator
  }
})