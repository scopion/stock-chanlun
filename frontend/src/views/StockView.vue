<template>
  <div class="layout">
    <!-- Nav -->
    <nav class="nav">
      <div class="nav-inner">
        <router-link to="/" class="nav-brand">ChanStock</router-link>
        <div class="nav-links">
          <router-link to="/" class="nav-link">首页</router-link>
          <router-link to="/screen" class="nav-link">选股</router-link>
          <router-link to="/watchlist" class="nav-link">自选股</router-link>
        </div>
        <div class="nav-actions">
          <!-- AI 模型切换 -->
          <div class="ai-model-switch">
            <button
              class="model-btn"
              :class="{ active: store.aiModel === 'deepseek' }"
              @click="switchModel('deepseek')"
              title="DeepSeek"
            >DS</button>
            <button
              class="model-btn"
              :class="{ active: store.aiModel === 'gemini' }"
              @click="switchModel('gemini')"
              title="Gemini"
            >GM</button>
          </div>
          <button class="btn btn-ghost" @click="loadData" :disabled="loadingAny">
            {{ loadingAny ? '加载中...' : '刷新' }}
          </button>
          <button class="btn btn-ghost" @click="toggleWatch" :class="{ 'btn-danger': isWatching }">
            {{ isWatching ? '取消自选' : '+自选' }}
          </button>
        </div>
      </div>
    </nav>

    <!-- 全局加载骨架屏 -->
    <div v-if="loadingAny" class="loading-overlay">
      <div class="loading-progress">
        <div class="loading-steps">
          <div v-for="step in loadingSteps" :key="step.key" class="loading-step" :class="step.status">
            <div class="step-dot" />
            <span class="step-label">{{ step.label }}</span>
          </div>
        </div>
        <div class="spinner" />
      </div>
    </div>

    <div v-else-if="error" class="error-page">
      <div class="error-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
      </div>
      <p class="error-message">{{ error }}</p>
      <button class="btn btn-primary" @click="loadData">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
        </svg>
        重试（R键）
      </button>
    </div>

    <div v-else class="main-grid">
      <!-- Left: Stock info -->
      <aside class="sidebar">
        <div class="card stock-info-card">
          <div class="stock-header">
            <div>
              <div class="stock-code-label mono">{{ stockCode }}</div>
              <div class="stock-name-label">{{ headerQuote?.name || stockCode }}</div>
            </div>
            <div class="stock-price-block">
              <div class="price-current mono">
                {{ headerQuote?.price != null ? headerQuote.price.toFixed(2) : '—' }}
              </div>
              <div
                class="price-change mono"
                :class="changeClass"
              >
                {{ changeText }}
              </div>
            </div>
          </div>

          <div class="price-stats">
            <div class="stat-row">
              <span class="stat-label">开盘</span>
              <span class="stat-value mono">{{ statPrice(headerQuote?.open) }}</span>
            </div>
            <div class="stat-row">
              <span class="stat-label">最高</span>
              <span class="stat-value mono price-up">{{ statPrice(headerQuote?.high) }}</span>
            </div>
            <div class="stat-row">
              <span class="stat-label">最低</span>
              <span class="stat-value mono price-down">{{ statPrice(headerQuote?.low) }}</span>
            </div>
            <div class="stat-row">
              <span class="stat-label">成交量</span>
              <span class="stat-value mono">{{ formatVolume(headerQuote?.volume) || '—' }}</span>
            </div>
          </div>
        </div>

        <!-- Level selector -->
        <div class="card">
          <div class="card-title">分析级别 <span class="level-hint">快捷键: 1/5/D/W/M</span></div>
          <div class="level-tabs">
            <button
              v-for="lv in levels"
              :key="lv.value"
              class="level-tab"
              :class="{ active: currentLevel === lv.value }"
              @click="changeLevel(lv.value)"
            >{{ lv.label }}</button>
          </div>
        </div>

        <!-- Trend info -->
        <div class="card">
          <div class="card-title">走势判断</div>
          <div class="trend-info">
            <div class="trend-badge" :class="trendClass">
              {{ store.chanlunResult?.trend || '—' }}
            </div>
            <div class="trend-desc">
              {{ store.chanlunResult?.summary || '暂无数据' }}
            </div>
          </div>
        </div>

        <!-- Signals -->
        <SignalCard :signals="store.chanlunResult?.signals || []" :updated-at="store.chanlunUpdatedAt" />
      </aside>

      <!-- Center: Chart -->
      <div class="chart-area">
        <div class="chart-header">
          <div class="chart-header-left">
            <div class="level-tabs chart-level-tabs">
              <button
                v-for="lv in levels"
                :key="lv.value"
                class="level-tab"
                :class="{ active: currentLevel === lv.value }"
                @click="changeLevel(lv.value)"
              >{{ lv.label }}</button>
            </div>
            <!-- 时间筛选 -->
            <div class="date-filter" :class="{ 'has-filter': startDate || endDate }">
              <button class="date-filter-toggle" @click="toggleDatePanel" :class="{ active: startDate || endDate }">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                  <line x1="16" y1="2" x2="16" y2="6"/>
                  <line x1="8" y1="2" x2="8" y2="6"/>
                  <line x1="3" y1="10" x2="21" y2="10"/>
                </svg>
                <span v-if="!startDate && !endDate">时间筛选</span>
                <span v-else class="date-filter-active-text">{{ formatFilterText() }}</span>
              </button>
              <div v-if="showDatePanel" class="date-panel">
                <div class="date-panel-row">
                  <label class="date-panel-label">开始日期</label>
                  <input
                    type="date"
                    v-model="startDate"
                    :max="endDate || undefined"
                    class="date-panel-input"
                  />
                </div>
                <div class="date-panel-row">
                  <label class="date-panel-label">结束日期</label>
                  <input
                    type="date"
                    v-model="endDate"
                    :min="startDate || undefined"
                    class="date-panel-input"
                  />
                </div>
                <div class="date-panel-actions">
                  <button class="date-panel-reset" @click="resetDateFilter" v-if="startDate || endDate">清除</button>
                  <button class="date-panel-apply" @click="applyDateFilter">应用</button>
                </div>
              </div>
            </div>
          </div>
          <div class="chart-actions">
            <IndicatorSelector />
          </div>
          <span v-if="store.klineUpdatedAt" class="chart-timestamp">K线 {{ store.klineUpdatedAt }}</span>
        </div>

        <!-- 主图区域上方：基本资料（与左侧行情互补） -->
        <div v-if="infoPanelRows.length > 0" class="company-info card">
          <div class="company-info-head">
            <span class="company-info-title">基本资料</span>
            <span v-if="stockInfo?.名称" class="company-info-name">{{ stockInfo.名称 }}</span>
          </div>
          <div class="company-info-grid">
            <div
              v-for="row in infoPanelRows"
              :key="row.key"
              class="company-info-cell"
            >
              <span class="ci-label">{{ row.label }}</span>
              <span
                class="ci-value mono"
                :class="row.valueClass"
              >{{ row.value }}</span>
            </div>
          </div>
        </div>

        <KLineChart
          ref="klineChartRef"
          :klines="store.klines"
          :bis="store.chanlunResult?.bis || []"
          :xiangs="store.chanlunResult?.xiangs || []"
          :zhongshus="store.chanlunResult?.zhongshus || []"
          :signals="store.chanlunResult?.signals || []"
          :ai-signal="store.aiSignal"
          :support-resistance="store.chanlunResult?.supportResistance || []"
          :indicators="store.indicators"
          @zoom-change="onZoomChange"
        />
        <VolumeChart v-if="store.indicators.volume" :klines="store.klines" :zoom-start="zoomStart" :zoom-end="zoomEnd" class="sub-chart" />
        <MACDChart v-if="store.indicators.macd" :klines="store.klines" :zoom-start="zoomStart" :zoom-end="zoomEnd" class="sub-chart" />
        <RSIChart v-if="store.indicators.rsi" :klines="store.klines" :zoom-start="zoomStart" :zoom-end="zoomEnd" class="sub-chart" />
        <SKDJChart v-if="store.indicators.skdj" :klines="store.klines" :zoom-start="zoomStart" :zoom-end="zoomEnd" class="sub-chart" />
      </div>

      <!-- 盘口 / 板块 / 个股新闻（K 线与策略之间的竖栏） -->
      <aside class="chart-rail">
        <div class="card rail-card">
          <div class="card-title">五档盘口</div>
          <div v-if="hasDepth" class="depth-wrap">
            <div class="depth-head">
              <span />
              <span class="dh-p">价格</span>
              <span class="dh-v">量</span>
            </div>
            <div
              v-for="(row, i) in depthAsks"
              :key="'a-' + i"
              class="depth-row depth-sell"
            >
              <span class="depth-lab">卖{{ 5 - i }}</span>
              <span class="mono depth-price">{{ fmtDepthPrice(row.price) }}</span>
              <span class="mono depth-vol">{{ fmtDepthVol(row.volume) }}</span>
            </div>
            <div class="depth-divider" />
            <div
              v-for="(row, i) in depthBids"
              :key="'b-' + i"
              class="depth-row depth-buy"
            >
              <span class="depth-lab">买{{ i + 1 }}</span>
              <span class="mono depth-price">{{ fmtDepthPrice(row.price) }}</span>
              <span class="mono depth-vol">{{ fmtDepthVol(row.volume) }}</span>
            </div>
          </div>
          <p v-else class="rail-empty">暂无盘口数据</p>
        </div>

        <div class="card rail-card">
          <div class="card-title">所属板块</div>
          <div v-if="extras?.boards?.industry" class="sector-main mono">{{ extras.boards.industry }}</div>
          <p v-else-if="boardHighlightRows.length" class="rail-hint">行业未标注</p>
          <p v-else class="rail-empty">暂无板块资料</p>
          <ul v-if="boardHighlightRows.length" class="board-highlights">
            <li v-for="(h, idx) in boardHighlightRows" :key="'bh-' + idx">
              <span class="bh-lab">{{ h.label }}</span>
              <span class="bh-val mono">{{ h.value }}</span>
            </li>
          </ul>
        </div>

        <div class="card rail-card rail-card-news">
          <div class="card-title">公司新闻</div>
          <div v-if="extras?.news?.length" class="news-rail-list">
            <template v-for="(n, idx) in extras.news" :key="'sn-' + idx">
              <a
                v-if="n.url"
                :href="n.url"
                target="_blank"
                rel="noopener noreferrer"
                class="news-rail-item"
              >
                <span class="news-rail-title">{{ n.title }}</span>
                <span class="news-rail-meta">
                  <span v-if="n.source" class="news-rail-src">{{ n.source }}</span>
                  <span v-if="n.time" class="news-rail-time">{{ n.time }}</span>
                </span>
              </a>
              <div v-else class="news-rail-item news-rail-item--nolink">
                <span class="news-rail-title">{{ n.title }}</span>
                <span class="news-rail-meta">
                  <span v-if="n.source" class="news-rail-src">{{ n.source }}</span>
                  <span v-if="n.time" class="news-rail-time">{{ n.time }}</span>
                </span>
              </div>
            </template>
          </div>
          <p v-else class="rail-empty">暂无相关新闻</p>
        </div>
      </aside>

      <!-- Right: AI Strategy + Notes -->
      <aside class="sidebar-right">
        <AIChat :stock-code="stockCode" />
        <CommentSection :stock-code="stockCode" />
        <StrategyCard :signal="store.aiSignal" :updated-at="store.aiUpdatedAt" />
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useChanlunStore, type LevelOption } from '../stores/chanlun'
import { useCommentStore } from '../stores/comment'
import { stockApi, type StockInfoFields, type StockExtras, type Quote } from '../api/stock'
import toast from '../composables/useToast'
import KLineChart from '../components/Chart/KLineChart.vue'
import VolumeChart from '../components/Chart/VolumeChart.vue'
import MACDChart from '../components/Chart/MACDChart.vue'
import RSIChart from '../components/Chart/RSIChart.vue'
import SKDJChart from '../components/Chart/SKDJChart.vue'
import SignalCard from '../components/Signal/SignalCard.vue'
import StrategyCard from '../components/Signal/StrategyCard.vue'
import IndicatorSelector from '../components/IndicatorSelector.vue'
import CommentSection from '../components/Signal/CommentSection.vue'
import AIChat from '../components/AIChat.vue'

const route = useRoute()
const store = useChanlunStore()
const commentStore = useCommentStore()
const klineChartRef = ref<InstanceType<typeof KLineChart> | null>(null)

const zoomStart = ref(0)
const zoomEnd = ref(100)

function onZoomChange(start: number, end: number) {
  zoomStart.value = start
  zoomEnd.value = end
}

const stockCode = computed(() => route.params.code as string)
const currentLevel = computed(() => store.currentLevel)
const loadingAny = computed(() =>
  store.loadingKline || store.loadingChanlun || store.loadingAI
)

const loadingSteps = computed(() => [
  { key: 'kline', label: 'K线数据', status: store.loadingKline ? 'loading' : store.klines.length ? 'done' : 'pending' },
  { key: 'chanlun', label: '缠论分析', status: store.loadingChanlun ? 'loading' : store.chanlunResult ? 'done' : 'pending' },
  { key: 'ai', label: 'AI策略', status: store.loadingAI ? 'loading' : store.aiSignal ? 'done' : 'pending' },
])

const error = computed(() =>
  store.errorKline || store.errorChanlun || store.errorAI
)
const quote = ref<Quote | null>(null)
const stockInfo = ref<StockInfoFields | null>(null)
const extras = ref<StockExtras | null>(null)
const isWatching = ref(false)

// 时间筛选
function getOneYearAgo(): string {
  const date = new Date()
  date.setFullYear(date.getFullYear() - 1)
  return date.toISOString().split('T')[0]
}

const startDate = ref(getOneYearAgo())
const endDate = ref('')
const showDatePanel = ref(false)

function toggleDatePanel() {
  showDatePanel.value = !showDatePanel.value
}

function formatFilterText() {
  if (startDate.value && endDate.value) {
    return `${startDate.value} ~ ${endDate.value}`
  } else if (startDate.value) {
    return `${startDate.value} 至今`
  } else if (endDate.value) {
    return `~ ${endDate.value}`
  }
  return '时间筛选'
}

function resetDateFilter() {
  startDate.value = getOneYearAgo()
  endDate.value = ''
  showDatePanel.value = false
  store.loadAll(stockCode.value, currentLevel.value)
}

function applyDateFilter() {
  showDatePanel.value = false
  store.loadAll(stockCode.value, currentLevel.value, startDate.value || undefined, endDate.value || undefined)
}

function _num(v: unknown): number | null {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function statPrice(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(2)
}

/** 左侧报价区：合并 /quote 与 /info，任一来源有有效现价即展示；避免 quote 对象不完整时全是「—」 */
const headerQuote = computed((): Quote | null => {
  const q = quote.value
  const s = stockInfo.value as Record<string, unknown> | null
  if (!q && !s) return null

  const price = _num(q?.price) ?? _num(s?.['现价'])
  if (price == null) return null

  const name =
    (q?.name != null && String(q.name).trim() !== '' ? String(q.name) : '') ||
    (s?.['名称'] != null ? String(s['名称']).trim() : '') ||
    ''
  const code = String(q?.code ?? s?.['代码'] ?? stockCode.value)

  return {
    code,
    name,
    price,
    change_pct: _num(q?.change_pct) ?? _num(s?.['涨跌幅']) ?? 0,
    volume: _num(q?.volume) ?? _num(s?.['成交量']) ?? 0,
    amount: _num(q?.amount) ?? _num(s?.['成交额']) ?? 0,
    high: _num(q?.high) ?? _num(s?.['最高']) ?? 0,
    low: _num(q?.low) ?? _num(s?.['最低']) ?? 0,
    open: _num(q?.open) ?? _num(s?.['今开']) ?? 0,
    prev_close: _num(q?.prev_close) ?? _num(s?.['昨收']) ?? 0,
  }
})

const levels = [
  { value: '1min' as LevelOption, label: '1分' },
  { value: '5min' as LevelOption, label: '5分' },
  { value: '15min' as LevelOption, label: '15分' },
  { value: '30min' as LevelOption, label: '30分' },
  { value: '60min' as LevelOption, label: '60分' },
  { value: 'daily' as LevelOption, label: '日线' },
  { value: 'weekly' as LevelOption, label: '周线' },
  { value: 'monthly' as LevelOption, label: '月线' },
]

const changeClass = computed(() => {
  const hq = headerQuote.value
  if (!hq) return ''
  return hq.change_pct > 0 ? 'price-up' : hq.change_pct < 0 ? 'price-down' : 'price-flat'
})

const changeText = computed(() => {
  const hq = headerQuote.value
  if (!hq) return ''
  const pct = hq.change_pct
  return `${pct > 0 ? '+' : ''}${pct?.toFixed(2) || 0}%`
})

const trendClass = computed(() => {
  const t = store.chanlunResult?.trend
  if (t === '上涨') return 'trend-up'
  if (t === '下跌') return 'trend-down'
  return 'trend-side'
})

type InfoRow = { key: string; label: string; value: string; valueClass?: string }

function fmtRatio(v?: number): string {
  if (v == null || Number.isNaN(v) || v === 0) return '—'
  return v.toFixed(2)
}

function fmtAmount(v?: number): string {
  if (v == null || Number.isNaN(v) || v === 0) return '—'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + ' 亿'
  if (v >= 1e4) return (v / 1e4).toFixed(2) + ' 万'
  return v.toFixed(0)
}

const infoPanelRows = computed((): InfoRow[] => {
  const s = stockInfo.value
  if (!s) return []
  const rows: InfoRow[] = []
  const push = (
    key: string,
    label: string,
    value: string,
    valueClass?: string
  ) => {
    if (value !== '—') rows.push({ key, label, value, valueClass })
  }
  const chg = (s as any).涨跌额
  let chgClass: string | undefined
  if (chg != null && !Number.isNaN(chg)) {
    if (chg > 0) chgClass = 'price-up'
    else if (chg < 0) chgClass = 'price-down'
  }
  push('pe', '市盈率', fmtRatio((s as any).市盈率))
  push('pb', '市净率', fmtRatio((s as any).市净率))
  if ((s as any).振幅 != null && !Number.isNaN((s as any).振幅) && (s as any).振幅 !== 0) {
    push('amp', '振幅', `${(s as any).振幅.toFixed(2)}%`)
  }
  push('amt', '成交额', fmtAmount((s as any).成交额))
  if (chg != null && !Number.isNaN(chg)) {
    const t = `${chg > 0 ? '+' : ''}${chg.toFixed(2)}`
    push('chg_amt', '涨跌额', t, chgClass)
  }
  push('prev', '昨收', (s as any).昨收 != null && !Number.isNaN((s as any).昨收) && (s as any).昨收 !== 0 ? (s as any).昨收.toFixed(2) : '—')
  return rows
})

const depthAsks = computed(() => extras.value?.depth?.asks ?? [])
const depthBids = computed(() => extras.value?.depth?.bids ?? [])
const hasDepth = computed(() => {
  const d = extras.value?.depth
  if (!d) return false
  const ok = (rows: { price: number; volume: number }[]) =>
    rows.some(r => r.price > 0 || r.volume > 0)
  return ok(d.asks) || ok(d.bids)
})

/** 与顶部「行业」主标题去重，避免列表里再显示一行行业 */
const boardHighlightRows = computed(() => {
  const list = extras.value?.boards?.highlights ?? []
  return list.filter(h => h.label !== '行业' && !/^行业/.test(h.label))
})

function fmtDepthPrice(p: number) {
  if (p == null || Number.isNaN(p) || p <= 0) return '—'
  return p.toFixed(2)
}

function fmtDepthVol(v: number) {
  if (v == null || Number.isNaN(v) || v <= 0) return '—'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
  return String(Math.round(v))
}

async function loadData() {
  const code = stockCode.value
  if (!code) return
  await store.loadAll(code, currentLevel.value, startDate.value || undefined, endDate.value || undefined)

  const settled = await Promise.allSettled([
    stockApi.quote(code),
    stockApi.info(code),
    stockApi.extras(code, 8),
  ])
  if (settled[0].status === 'fulfilled') quote.value = settled[0].value.data as Quote
  else quote.value = null
  if (settled[1].status === 'fulfilled') {
    const inf = settled[1].value.data.info
    stockInfo.value = inf && Object.keys(inf).length ? inf : null
  } else stockInfo.value = null
  if (settled[2].status === 'fulfilled') extras.value = settled[2].value.data
  else extras.value = null

  // 加载评论笔记
  commentStore.fetchComments(code)
}

async function changeLevel(level: LevelOption) {
  await store.loadAll(stockCode.value, level)
}

async function toggleWatch() {
  if (isWatching.value) {
    await stockApi.removeWatch(stockCode.value)
    isWatching.value = false
    toast.success('已从自选股移除')
  } else {
    await stockApi.addWatch(stockCode.value)
    isWatching.value = true
    toast.success('已添加到自选股')
  }
}

async function switchModel(model: string) {
  if (model === store.aiModel) return
  await store.setAiModel(model)
  await store.loadAll(stockCode.value, store.currentLevel)
}

function formatVolume(v?: number) {
  if (!v) return '—'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
  return v.toString()
}

// 键盘快捷键
function handleKeydown(e: KeyboardEvent) {
  // 忽略输入框中的按键
  if ((e.target as HTMLElement).tagName === 'INPUT' || (e.target as HTMLElement).tagName === 'TEXTAREA') {
    return
  }

  switch (e.key) {
    case 'r':
    case 'R':
      if (!loadingAny.value) loadData()
      break
    case '1':
      changeLevel('1min')
      break
    case '5':
      changeLevel('5min')
      break
    case 'd':
    case 'D':
      changeLevel('daily')
      break
    case 'w':
    case 'W':
      changeLevel('weekly')
      break
    case 'm':
    case 'M':
      changeLevel('monthly')
      break
  }
}

onMounted(() => {
  loadData()
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})

watch(() => route.params.code, loadData)
</script>

<style scoped>
.layout { min-height: 100vh; }

.nav-actions { display: flex; gap: 8px; margin-left: auto; }

.loading-overlay {
  position: fixed;
  inset: 0;
  z-index: 999;
  background: var(--bg-base);
  display: flex;
  align-items: center;
  justify-content: center;
}

.loading-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
}

.loading-steps {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 200px;
}

.loading-step {
  display: flex;
  align-items: center;
  gap: 10px;
}

.step-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: background 0.3s;
}

.loading-step.pending .step-dot { background: var(--border); }
.loading-step.loading .step-dot {
  background: var(--accent-blue);
  animation: pulse 1s ease-in-out infinite;
}
.loading-step.done .step-dot { background: var(--accent-green); }

.step-label {
  font-size: 0.85rem;
  transition: color 0.3s;
}
.loading-step.pending .step-label { color: var(--text-muted); }
.loading-step.loading .step-label { color: var(--text-primary); }
.loading-step.done .step-label { color: var(--accent-green); }

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.8); }
}

@keyframes spin { to { transform: rotate(360deg); } }
.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border);
  border-top-color: var(--accent-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.error-page {
  text-align: center;
  padding: 80px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}
.error-icon {
  color: var(--accent-red);
  opacity: 0.6;
}
.error-message {
  color: var(--text-secondary);
  font-size: 0.95rem;
  margin: 0;
  max-width: 320px;
}
.error-page .btn {
  margin-top: 8px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.main-grid {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr) 272px 280px;
  gap: 16px;
  padding: 16px 24px;
  max-width: 1760px;
  margin: 0 auto;
  align-items: start;
}

.sidebar, .chart-rail { display: flex; flex-direction: column; gap: 12px; }

.sidebar-right {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  height: calc(100vh - 88px);
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
  position: sticky;
  top: 0;
  align-self: start;
}
.sidebar-right::-webkit-scrollbar { width: 5px; }
.sidebar-right::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

.chart-rail {
  min-width: 0;
  max-height: calc(100vh - 72px);
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
.chart-rail::-webkit-scrollbar { width: 5px; }
.chart-rail::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

.rail-card { padding: 12px 14px; }
.rail-card-news { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.rail-empty {
  margin: 6px 0 0;
  font-size: 0.75rem;
  color: var(--text-muted);
}
.rail-hint { margin: 4px 0 0; font-size: 0.72rem; color: var(--text-secondary); }

.depth-wrap { margin-top: 4px; }
.depth-head {
  display: grid;
  grid-template-columns: 2.2rem 1fr 1fr;
  gap: 4px;
  font-size: 0.65rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 6px;
}
.dh-p, .dh-v { text-align: right; }
.depth-row {
  display: grid;
  grid-template-columns: 2.2rem 1fr 1fr;
  gap: 4px;
  align-items: center;
  font-size: 0.78rem;
  padding: 3px 0;
}
.depth-lab { color: var(--text-muted); font-size: 0.72rem; }
.depth-price { text-align: right; font-weight: 600; }
.depth-vol { text-align: right; font-size: 0.72rem; color: var(--text-secondary); }
.depth-sell .depth-price { color: var(--accent-green); }
.depth-buy .depth-price { color: var(--accent-red); }
.depth-divider {
  height: 1px;
  background: var(--border);
  margin: 6px 0;
  opacity: 0.85;
}

.sector-main {
  margin-top: 6px;
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--accent-blue);
  line-height: 1.35;
}
.board-highlights {
  list-style: none;
  margin: 10px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.board-highlights li {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}
.board-highlights li:last-child { border-bottom: none; padding-bottom: 0; }
.bh-lab { font-size: 0.65rem; color: var(--text-muted); }
.bh-val { font-size: 0.74rem; color: var(--text-secondary); word-break: break-all; }

.news-rail-list {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  flex: 1;
  min-height: 120px;
  max-height: 320px;
  padding-right: 2px;
}
.news-rail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  text-decoration: none;
  color: inherit;
  transition: border-color 0.15s, background 0.15s;
}
.news-rail-item:hover:not(.news-rail-item--nolink) {
  border-color: var(--accent-blue);
  background: var(--bg-hover);
}
.news-rail-item--nolink {
  cursor: default;
  opacity: 0.85;
}
.news-rail-title {
  font-size: 0.78rem;
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-primary);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.news-rail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 0.65rem;
  color: var(--text-muted);
}
.news-rail-src {
  color: var(--accent-blue);
  font-weight: 600;
}

.stock-info-card { padding: 16px; }
.stock-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}
.stock-code-label { font-size: 0.75rem; color: var(--text-muted); }
.stock-name-label { font-size: 1.1rem; font-weight: 700; }
.price-current { font-size: 1.8rem; font-weight: 700; }
.price-change { font-size: 0.9rem; margin-top: 4px; }

.price-stats { display: flex; flex-direction: column; gap: 8px; }
.stat-row { display: flex; justify-content: space-between; }
.stat-label { color: var(--text-muted); font-size: 0.85rem; }
.stat-value { font-size: 0.85rem; }

.trend-info { display: flex; flex-direction: column; gap: 8px; }
.trend-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 0.85rem;
  font-weight: 600;
  width: fit-content;
}
.trend-up { background: rgba(239, 68, 68, 0.14); color: var(--accent-red); border: 1px solid rgba(239, 68, 68, 0.25); }
.trend-down { background: rgba(34, 197, 94, 0.14); color: var(--accent-green); border: 1px solid rgba(34, 197, 94, 0.25); }
.trend-side { background: rgba(245, 158, 11, 0.12); color: var(--accent-amber); border: 1px solid rgba(245, 158, 11, 0.28); }
.trend-desc { font-size: 0.8rem; color: var(--text-secondary); line-height: 1.5; }

.ai-model-switch {
  display: flex;
  gap: 4px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 4px;
}
.model-btn {
  padding: 5px 12px;
  border-radius: 7px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
}
.model-btn.active {
  background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%);
  color: #fff;
  box-shadow: 0 2px 10px rgba(14, 165, 233, 0.35);
}
.model-btn:hover:not(.active) { color: var(--text-primary); background: rgba(255, 255, 255, 0.06); }

.chart-area { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.chart-header { display: flex; align-items: center; gap: 8px; }
.chart-level-tabs { flex-shrink: 0; }
.chart-actions { margin-left: auto; }
.chart-timestamp { font-size: 0.65rem; color: var(--text-muted); font-family: var(--font-mono); white-space: nowrap; }
.sub-chart { height: 100px; }

.company-info {
  padding: 12px 14px;
  flex-shrink: 0;
}
.company-info-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.company-info-title {
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.company-info-name {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 55%;
}
.company-info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: 10px 14px;
}
.company-info-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.ci-label {
  font-size: 0.68rem;
  color: var(--text-muted);
}
.ci-value {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-primary);
}

/* 时间筛选器样式 */
.chart-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.date-filter {
  position: relative;
}

.date-filter-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.75rem;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.date-filter-toggle:hover {
  border-color: var(--accent-blue);
  color: var(--text-primary);
}

.date-filter-toggle.active {
  background: rgba(14, 165, 233, 0.1);
  border-color: var(--accent-blue);
  color: var(--accent-blue);
}

.date-filter-active-text {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.date-panel {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  z-index: 100;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
  min-width: 220px;
}

.date-panel-row {
  margin-bottom: 12px;
}

.date-panel-row:last-of-type {
  margin-bottom: 14px;
}

.date-panel-label {
  display: block;
  font-size: 0.7rem;
  color: var(--text-muted);
  margin-bottom: 6px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.date-panel-input {
  width: 100%;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 0.8rem;
  color: var(--text-primary);
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}

.date-panel-input:focus {
  border-color: var(--accent-blue);
}

.date-panel-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.date-panel-reset {
  padding: 6px 14px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.75rem;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
}

.date-panel-reset:hover {
  color: var(--accent-red);
  border-color: var(--accent-red);
}

.date-panel-apply {
  padding: 6px 14px;
  background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%);
  border: none;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 600;
  color: #fff;
  cursor: pointer;
  transition: all 0.15s;
}

.date-panel-apply:hover {
  filter: brightness(1.1);
}

@media (max-width: 1320px) {
  .main-grid { grid-template-columns: 220px minmax(0, 1fr) 280px; }
  .chart-rail { display: none; }
}
@media (max-width: 1200px) {
  .main-grid { grid-template-columns: 200px 1fr; }
  .sidebar-right { display: none; }
}
@media (max-width: 768px) {
  .main-grid { grid-template-columns: 1fr; }
  .sidebar { display: none; }
}
</style>