<template>
  <PullRefresh :refreshing="refreshing" @refresh="handleRefresh">
  <div class="sector-view">
    <!-- 头部 -->
    <div class="page-head">
      <button class="back-btn" @click="$router.back()">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
      </button>
      <div class="ph-info">
        <h1 class="ph-title">{{ sectorName }}</h1>
        <span class="ph-meta">{{ total }} 只成分股 · {{ boardType === 'industry' ? '行业' : '概念' }}板块</span>
      </div>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="loading-wrap">
      <div v-for="i in 10" :key="i" class="skeleton-card" />
    </div>

    <!-- 错误 -->
    <div v-else-if="error" class="error-wrap">
      <p>{{ error }}</p>
      <button class="btn btn-ghost" @click="fetchData">重试</button>
    </div>

    <!-- 空 -->
    <div v-else-if="stocks.length === 0" class="empty-wrap">
      <p>该板块暂无成分股数据</p>
    </div>

    <!-- 成分股列表 -->
    <div v-else class="stock-list">
      <div
        v-for="s in stocks"
        :key="s.code"
        class="stock-row"
        @click="go(`/m/stock/${s.code}`)"
      >
        <div class="sr-rank">
          <span class="rank-num" :class="rankClass(s.rank)">#{{ s.rank }}</span>
        </div>
        <div class="sr-left">
          <div class="sr-name">{{ s.name }}</div>
          <div class="sr-code mono">{{ s.code }}</div>
        </div>
        <div class="sr-right">
          <div class="sr-price mono">{{ s.price > 0 ? s.price.toFixed(2) : '—' }}</div>
          <div
            class="sr-pct mono"
            :class="s.change_pct >= 0 ? 'price-up' : s.change_pct < 0 ? 'price-down' : 'price-flat'"
          >
            {{ s.change_pct >= 0 ? '+' : '' }}{{ s.change_pct.toFixed(2) }}%
          </div>
        </div>
        <button
          class="watch-btn"
          :class="{ added: isWatched(s.code) }"
          @click.stop="toggleWatch(s.code)"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
  </PullRefresh>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { stockApi, type SectorStock } from '@/api/stock'
import { useWatchlistStore } from '@/stores/watchlist'
import toast from '@/composables/useToast'
import PullRefresh from '@/mobile/components/PullRefresh.vue'

const route = useRoute()
const router = useRouter()
const wlStore = useWatchlistStore()

const sectorName = computed(() => String(route.params.name || ''))
const stocks = ref<SectorStock[]>([])
const total = ref(0)
const boardType = ref<'industry' | 'concept' | null>(null)
const loading = ref(false)
const refreshing = ref(false)
const error = ref('')

const watchedCodes = computed(() => new Set(wlStore.stocks.map(s => s.code)))
function isWatched(code: string) { return watchedCodes.value.has(code) }

async function toggleWatch(code: string) {
  try {
    if (isWatched(code)) {
      await wlStore.removeStock(code)
      toast.info('已从自选股移除')
    } else {
      await wlStore.addStock(code)
      toast.success('已添加到自选股')
    }
  } catch {
    // 已在 store 回滚
  }
}

function rankClass(rank: number): string {
  if (rank === 1) return 'rank-gold'
  if (rank === 2) return 'rank-silver'
  if (rank === 3) return 'rank-bronze'
  return ''
}

function go(path: string) { router.push(path) }

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

async function handleRefresh() {
  refreshing.value = true
  await fetchData()
  refreshing.value = false
}

onMounted(() => {
  fetchData()
  wlStore.fetchWatchlist()
})
</script>

<style scoped>
.sector-view {
  padding: 0 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Head */
.page-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}
.back-btn {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  border-radius: 6px;
  transition: color 0.15s, background 0.15s;
  flex-shrink: 0;
}
.back-btn:active { color: var(--text-primary); background: var(--bg-hover); }
.ph-info { flex: 1; min-width: 0; }
.ph-title {
  font-size: 1.05rem;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ph-meta { font-size: 0.72rem; color: var(--text-muted); }

/* Loading */
.loading-wrap { display: flex; flex-direction: column; gap: 6px; }
.skeleton-card {
  height: 64px;
  border-radius: 10px;
  background: var(--bg-card);
  animation: shimmer 1.5s infinite;
  background: linear-gradient(90deg, var(--bg-card) 25%, rgba(255,255,255,0.04) 50%, var(--bg-card) 75%);
  background-size: 200% 100%;
}
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

/* Error / Empty */
.error-wrap, .empty-wrap {
  text-align: center;
  padding: 40px 24px;
  color: var(--text-muted);
  font-size: 0.85rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

/* Stock list */
.stock-list { display: flex; flex-direction: column; gap: 6px; }

.stock-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  cursor: pointer;
  color: inherit;
  font: inherit;
  text-align: left;
  width: 100%;
  transition: border-color 0.15s, background 0.15s;
  min-height: 60px;
}
.stock-row:active { border-color: var(--accent-blue); background: var(--bg-hover); }

.sr-rank {
  width: 32px;
  display: flex;
  justify-content: center;
  flex-shrink: 0;
}
.rank-num { font-size: 0.82rem; font-weight: 700; color: var(--text-muted); }
.rank-gold { color: #ffd700; }
.rank-silver { color: #c0c0c0; }
.rank-bronze { color: #cd7f32; }

.sr-left { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.sr-name { font-size: 0.9rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sr-code { font-size: 0.7rem; color: var(--text-muted); }

.sr-right { display: flex; flex-direction: column; align-items: flex-end; gap: 3px; min-width: 60px; }
.sr-price { font-size: 0.875rem; font-weight: 700; }
.sr-pct { font-size: 0.875rem; font-weight: 700; }

.watch-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: color 0.15s, background 0.15s;
  flex-shrink: 0;
}
.watch-btn.added { color: var(--accent-red); }
.watch-btn:not(.added):hover { color: var(--accent-red); }
</style>
