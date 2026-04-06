import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

// ─── Types ───────────────────────────────────────────────────────────────────

export interface KLine {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface Bi {
  id: string
  start: string
  end: string
  direction: 'up' | 'down'
  high: number
  low: number
}

export interface XiangSegment {
  id: string
  start: string
  end: string
  direction: 'up' | 'down'
  high: number
  low: number
}

export interface Zhongshu {
  id: string
  start: string
  end: string
  range_high: number
  range_low: number
}

export interface Signal {
  type: string
  level: string
  price: number
  datetime: string
  confidence: number
  stop_loss?: number
  take_profit?: number
  description: string
}

export interface StockScreenResult {
  code: string
  name: string
  price: number
  change_pct: number
  volume: number
  amount: number
  industry: string | null
  pe: number | null
  pb: number | null
  latest_signal: string | null
  latest_signal_date: string | null
  latest_signal_conf: number | null
  has_dual_cross: boolean
  dual_cross_date: string | null
  trend: string
}

export interface SupportResistance {
  type: 'support' | 'resistance'
  price: number
  source: string
  relatedId: string
  datetime: string
  strength: number
}

export interface HotStock {
  rank: number
  code: string
  name: string
  change_pct?: number
  volume?: number
}

/** 首页大盘概览：主要指数一行 */
export interface MarketOverviewIndex {
  code: string
  name: string
  price: number
  change_pct: number
}

export interface MarketOverview {
  indices: Record<string, MarketOverviewIndex>
  market_breadth: { advancers: number; decliners: number; unchanged: number }
  sectors: Array<{ name: string; change_pct: number; kind?: string }>
  sectors_top: Array<{ name: string; change_pct: number }>
  sectors_bottom: Array<{ name: string; change_pct: number }>
}

export interface MarketSector {
  name: string
  change_pct: number
  kind?: string
}

export interface NewsItem {
  title: string
  time: string
  source: string
  url: string
  digest: string
}

export interface Quote {
  code: string
  name: string
  price: number
  change_pct: number
  volume: number
  high: number
  low: number
  open: number
  prev_close: number
  amount: number
}

/** 腾讯行情接口解析的基本面/行情字段（与后端 get_stock_info 一致） */
export interface DepthLevel {
  price: number
  volume: number
}

export interface StockDepth {
  asks: DepthLevel[]
  bids: DepthLevel[]
}

export interface BoardHighlight {
  label: string
  value: string
}

export interface StockBoards {
  industry: string
  highlights: BoardHighlight[]
}

export interface StockSymbolNewsItem {
  title: string
  time: string
  source: string
  url: string
}

export interface StockExtras {
  code: string
  exchange: string
  depth: StockDepth
  boards: StockBoards
  news: StockSymbolNewsItem[]
}

export interface StockInfoFields {
  代码?: string
  名称?: string
  现价?: number
  涨跌幅?: number
  涨跌额?: number
  成交量?: number
  成交额?: number
  振幅?: number
  最高?: number
  最低?: number
  今开?: number
  昨收?: number
  市净率?: number
  市盈率?: number
}

export interface ChanlunResult {
  stock_code: string
  level: string
  trend: string
  summary: string
  bis: Bi[]
  xiangs: XiangSegment[]
  zhongshus: Zhongshu[]
  signals: Signal[]
  supportResistance: SupportResistance[]
}

export interface AISignal {
  stock_code: string
  level: string
  direction: string
  confidence: number
  risk_level: string
  entry_price?: number
  stop_loss?: number
  take_profit?: number
  holding_period: string
  description: string
  trend: string
  divergence?: { type: string; probability: number; description: string } | null
  resonance?: { 共振: boolean; direction?: string; levels?: string[]; description: string }
  llm?: {
    model: string
    used: boolean
    error?: string
  }
}

// ─── API Methods ────────────────────────────────────────────────────────────

export const stockApi = {
  search(q: string) {
    return api.get<{ stocks: { code: string; name: string }[]; total: number }>(
      `/stocks/search?q=${q}`
    )
  },

  hotStocks(limit = 15) {
    return api.get<{ stocks: HotStock[]; total: number; error?: string | null }>('/stocks/hot', {
      params: { limit },
      timeout: 60000,
    })
  },

  marketOverview() {
    return api.get<MarketOverview>('/market/overview', { timeout: 90000 })
  },

  news(limit = 10) {
    return api.get<{ items: NewsItem[] }>('/news', { params: { limit }, timeout: 20000 })
  },

  info(code: string) {
    return api.get<{ code: string; exchange: string; info: StockInfoFields }>(
      `/stocks/${code}/info`
    )
  },

  extras(code: string, newsLimit = 8) {
    return api.get<StockExtras>(`/stocks/${code}/extras`, {
      params: { news_limit: newsLimit },
      timeout: 45000,
    })
  },

  quote(code: string) {
    return api.get<Quote>(`/stocks/${code}/quote`)
  },

  kline(code: string, level: string, limit = 500) {
    return api.get<{ klines: KLine[]; total: number }>(
      `/stocks/${code}/kline?level=${level}&limit=${limit}`
    )
  },

  chanlun(code: string, level: string) {
    return api.get<ChanlunResult>(
      `/chanlun/${code}?level=${level}`
    )
  },

  aiSignal(code: string, level: string, model = 'deepseek') {
    return api.get<AISignal>(
      `/chanlun/${code}/ai?level=${level}&model=${model}`,
      { timeout: 120000 }
    )
  },

  watchlist() {
    return api.get<{ stocks: Quote[]; total: number }>('/watchlist')
  },

  addWatch(code: string) {
    return api.post(`/watchlist/${code}`)
  },

  removeWatch(code: string) {
    return api.delete(`/watchlist/${code}`)
  },

  getSettings() {
    return api.get<{ ai_model: string }>('/settings')
  },

  setAiModel(model: string) {
    return api.put<{ ai_model: string; ok: boolean }>('/settings', null, {
      params: { model },
    })
  },

  screenStocks(params: {
    change_pct_min?: number
    change_pct_max?: number
    volume_min?: number
    volume_max?: number
    industry?: string
    pe_max?: number
    pb_max?: number
    signals?: string
    dual_cross?: boolean
    level?: string
    pool_size?: number
  }) {
    const size = params.pool_size ?? 100
    return api.get<{ results: StockScreenResult[]; total: number }>(
      '/stocks/screen',
      { params, timeout: size >= 500 ? 180000 : 60000 }
    )
  },
}

export default api