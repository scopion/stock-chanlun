<template>
  <div class="layout">
    <nav class="nav">
      <div class="nav-inner">
        <router-link to="/" class="nav-brand">ChanStock</router-link>
        <div class="nav-links">
          <router-link to="/" class="nav-link">首页</router-link>
          <router-link to="/screen" class="nav-link">选股</router-link>
          <router-link to="/watchlist" class="nav-link">自选股</router-link>
        </div>
      </div>
    </nav>

    <div class="container">
      <!-- 面包屑 -->
      <div class="breadcrumb">
        <router-link to="/" class="bc-link">首页</router-link>
        <span class="bc-sep">/</span>
        <span class="bc-label">{{ sectorName }}</span>
      </div>

      <!-- 标题栏 -->
      <div class="page-header">
        <div class="ph-left">
          <h1 class="ph-title">{{ sectorName }}</h1>
          <span class="ph-count">{{ total }} 只成分股</span>
        </div>
        <div class="ph-right">
          <span class="ph-type-badge">{{ boardType === 'industry' ? '行业板块' : '概念板块' }}</span>
        </div>
      </div>

      <!-- 加载中 -->
      <div v-if="loading" class="skeleton-list">
        <div v-for="i in 12" :key="i" class="skeleton-row" />
      </div>

      <!-- 错误 -->
      <div v-else-if="error" class="error-state">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <p>{{ error }}</p>
        <button class="btn btn-primary" @click="fetchData">重试</button>
      </div>

      <!-- 空状态 -->
      <div v-else-if="stocks.length === 0" class="empty-state">
        <p>该板块暂无成分股数据</p>
      </div>

      <!-- 成分股表格 -->
      <div v-else class="stock-table">
        <div class="table-header">
          <span>排名</span>
          <span>名称</span>
          <span>代码</span>
          <span>现价</span>
          <span>涨跌幅</span>
          <span>换手率</span>
          <span>市盈率</span>
          <span>市净率</span>
          <span></span>
        </div>
        <div
          v-for="s in stocks"
          :key="s.code"
          class="table-row"
          @click="goToStock(s.code)"
        >
          <span class="rank-cell">
            <span class="rank-num" :class="rankClass(s.rank)">#{{ s.rank }}</span>
          </span>
          <span class="name-cell">{{ s.name }}</span>
          <span class="mono code-cell">{{ s.code }}</span>
          <span class="mono">{{ s.price > 0 ? s.price.toFixed(2) : '—' }}</span>
          <span class="mono" :class="s.change_pct >= 0 ? 'price-up' : 'price-down'">
            {{ s.change_pct >= 0 ? '+' : '' }}{{ s.change_pct.toFixed(2) }}%
          </span>
          <span class="mono secondary">
            {{ s.turnover_pct > 0 ? s.turnover_pct.toFixed(2) + '%' : '—' }}
          </span>
          <span class="mono secondary">
            {{ s.pe_ttm > 0 ? s.pe_ttm.toFixed(2) : '—' }}
          </span>
          <span class="mono secondary">
            {{ s.pb > 0 ? s.pb.toFixed(2) : '—' }}
          </span>
          <span class="action-cell">
            <button
              class="add-watch-btn"
              :class="{ added: isWatched(s.code) }"
              @click.stop="toggleWatch(s.code)"
            >
              {{ isWatched(s.code) ? '已自选' : '+自选' }}
            </button>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { stockApi, type SectorStock } from '@/api/stock'
import { useWatchlistStore } from '@/stores/watchlist'
import toast from '@/composables/useToast'

const route = useRoute()
const router = useRouter()
const watchlistStore = useWatchlistStore()

const sectorName = computed(() => String(route.params.name || ''))
const stocks = ref<SectorStock[]>([])
const total = ref(0)
const boardType = ref<'industry' | 'concept' | null>(null)
const loading = ref(true)
const error = ref('')

const watchedCodes = computed(() => new Set(watchlistStore.stocks.map(s => s.code)))

function isWatched(code: string) { return watchedCodes.value.has(code) }

async function toggleWatch(code: string) {
  try {
    if (isWatched(code)) {
      await watchlistStore.removeStock(code)
      toast.info('已从自选股移除')
    } else {
      await watchlistStore.addStock(code)
      toast.success('已添加到自选股')
    }
  } catch {
    // 已在 store 回滚
  }
}

function rankClass(rank: number): string {
  if (rank <= 3) return `rank-top${rank}`
  return ''
}

function goToStock(code: string) {
  router.push(`/stock/${code}`)
}

async function fetchData() {
  loading.value = true
  error.value = ''
  try {
    const res = await stockApi.sectorStocks(sectorName.value)
    stocks.value = res.data.stocks ?? []
    total.value = res.data.total ?? 0
    boardType.value = res.data.board_type as 'industry' | 'concept' | null
  } catch (e: any) {
    error.value = e?.message ?? '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchData()
  watchlistStore.fetchWatchlist()
})
</script>

<style scoped>
.layout { min-height: 100vh; }
.nav { border-bottom: 1px solid var(--border); background: var(--bg-primary); }
.nav-inner {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 24px;
  height: 52px;
  display: flex;
  align-items: center;
  gap: 24px;
}
.nav-brand { font-family: 'Outfit', sans-serif; font-size: 1.05rem; font-weight: 700; color: var(--text-primary); text-decoration: none; letter-spacing: -0.01em; }
.nav-links { display: flex; gap: 4px; }
.nav-link { padding: 4px 12px; border-radius: 6px; font-size: 0.85rem; color: var(--text-secondary); text-decoration: none; transition: color 0.15s, background 0.15s; }
.nav-link:hover { color: var(--text-primary); background: var(--bg-hover); }

.container {
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px 24px 48px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Breadcrumb */
.breadcrumb { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; }
.bc-link { color: var(--accent-blue); text-decoration: none; }
.bc-link:hover { text-decoration: underline; }
.bc-sep { color: var(--text-muted); }
.bc-label { color: var(--text-secondary); }

/* Header */
.page-header { display: flex; align-items: center; justify-content: space-between; }
.ph-left { display: flex; align-items: baseline; gap: 12px; }
.ph-title { font-size: 1.5rem; font-weight: 700; margin: 0; }
.ph-count { font-size: 0.85rem; color: var(--text-muted); }
.ph-type-badge {
  font-size: 0.72rem;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(56, 189, 248, 0.1);
  border: 1px solid rgba(56, 189, 248, 0.25);
  color: var(--accent-blue);
  font-weight: 600;
}

/* Skeleton */
.skeleton-list { display: flex; flex-direction: column; gap: 6px; }
.skeleton-row { height: 52px; background: var(--bg-card); border-radius: 8px; animation: shimmer 1.5s infinite; background: linear-gradient(90deg, var(--bg-card) 25%, rgba(255,255,255,0.04) 50%, var(--bg-card) 75%); background-size: 200% 100%; }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

/* Error / Empty */
.error-state, .empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 12px; padding: 80px 20px; text-align: center;
  color: var(--text-muted);
}
.error-state svg { color: var(--accent-red); }

/* Table */
.stock-table { display: flex; flex-direction: column; gap: 2px; }
.table-header, .table-row {
  display: grid;
  grid-template-columns: 60px 1fr 90px 90px 90px 80px 80px 80px 72px;
  align-items: center;
  padding: 12px 16px;
  border-radius: 8px;
}
.table-header {
  background: var(--bg-secondary);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
}
.table-row {
  background: var(--bg-card);
  cursor: pointer;
  transition: background 0.12s;
}
.table-row:hover { background: var(--bg-hover); }

.rank-cell { display: flex; align-items: center; }
.rank-num { font-size: 0.82rem; font-weight: 700; color: var(--text-muted); }
.rank-top1 { color: #ffd700; }
.rank-top2 { color: #c0c0c0; }
.rank-top3 { color: #cd7f32; }

.name-cell { font-weight: 600; font-size: 0.875rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.code-cell { color: var(--accent-blue); font-size: 0.78rem; }
.secondary { color: var(--text-secondary); font-size: 0.8rem; }

.action-cell { display: flex; justify-content: flex-end; }
.add-watch-btn {
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.72rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  min-height: 28px;
}
.add-watch-btn:hover {
  border-color: var(--accent-blue);
  color: var(--accent-blue);
}
.add-watch-btn.added {
  border-color: var(--accent-green);
  color: var(--accent-green);
  background: rgba(34, 197, 94, 0.08);
}
</style>
