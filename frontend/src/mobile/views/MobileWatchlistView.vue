<template>
  <div class="watchlist-view">
    <div class="page-head">
      <h2 class="page-title">我的自选</h2>
      <span class="page-count">{{ store.stocks.length }} 支</span>
    </div>

    <div v-if="store.loading" class="page-loading">
      <div v-for="i in 5" :key="i" class="skeleton w-skel" />
    </div>

    <div v-else-if="store.error" class="page-error">
      <p>{{ store.error }}</p>
      <button class="btn btn-ghost" @click="store.fetchWatchlist()">重试</button>
    </div>

    <div v-else-if="store.stocks.length === 0" class="page-empty">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="empty-icon">
        <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z"/>
        <path d="M12 6v6l4 2"/>
      </svg>
      <p>暂无自选股</p>
      <p class="empty-hint">在个股页面点击「+自选」添加</p>
    </div>

    <div v-else class="stock-list">
      <button
        v-for="s in store.stocks"
        :key="s.code"
        class="stock-row"
        @click="go(`/m/stock/${s.code}`)"
      >
        <div class="sr-left">
          <div class="sr-name">{{ s.name || s.code }}</div>
          <div class="sr-code mono">{{ s.code }}</div>
        </div>
        <div class="sr-center">
          <div class="sr-price mono">{{ s.price > 0 ? s.price.toFixed(2) : '—' }}</div>
          <div class="sr-vol">{{ fmtVol(s.volume) }}</div>
        </div>
        <div class="sr-right">
          <div
            class="sr-pct mono"
            :class="s.change_pct > 0 ? 'price-up' : s.change_pct < 0 ? 'price-down' : 'price-flat'"
          >{{ s.change_pct > 0 ? '+' : '' }}{{ s.change_pct.toFixed(2) }}%</div>
          <button
            class="remove-btn"
            @click.stop="remove(s.code)"
            title="删除自选"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
            </svg>
          </button>
        </div>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useWatchlistStore } from '@/stores/watchlist'

const router = useRouter()
const store = useWatchlistStore()

function fmtVol(v?: number) {
  if (!v) return '—'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
  return String(v)
}

function go(path: string) {
  router.push(path)
}

async function remove(code: string) {
  await store.removeStock(code)
}

onMounted(() => {
  store.fetchWatchlist()
})
</script>

<style scoped>
.watchlist-view {
  padding: 16px 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.page-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.page-title {
  font-size: 1rem;
  font-weight: 700;
}
.page-count {
  font-size: 0.78rem;
  color: var(--text-muted);
}

.page-loading {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.w-skel {
  height: 64px;
  border-radius: 10px;
}

.page-error {
  text-align: center;
  padding: 40px 24px;
  color: var(--accent-red);
  font-size: 0.85rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.page-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 60px 24px;
  color: var(--text-muted);
  text-align: center;
}
.empty-icon {
  color: var(--text-muted);
  margin-bottom: 8px;
}
.empty-hint {
  font-size: 0.78rem;
  color: var(--text-muted);
}

.stock-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.stock-row {
  display: flex;
  align-items: center;
  gap: 12px;
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
.stock-row:active {
  border-color: var(--accent-blue);
  background: var(--bg-hover);
}

.sr-left {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.sr-name {
  font-size: 0.9rem;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sr-code {
  font-size: 0.7rem;
  color: var(--text-muted);
}

.sr-center {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
  min-width: 72px;
}
.sr-price {
  font-size: 0.9rem;
  font-weight: 700;
}
.sr-vol {
  font-size: 0.65rem;
  color: var(--text-muted);
}

.sr-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}
.sr-pct {
  font-size: 0.85rem;
  font-weight: 700;
}

.remove-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.15s, background 0.15s;
}
.remove-btn:hover {
  color: var(--accent-red);
  background: rgba(239, 68, 68, 0.1);
}
</style>
