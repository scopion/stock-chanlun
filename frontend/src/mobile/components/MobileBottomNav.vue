<template>
  <nav class="tab-bar">
    <router-link to="/m" class="tab-item" :class="{ active: route.path === '/m' }" :exact="true">
      <div class="tab-icon-wrap">
        <svg class="tab-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
          <polyline points="9 22 9 12 15 12 15 22"/>
        </svg>
      </div>
      <span class="tab-label">首页</span>
    </router-link>

    <router-link to="/m/screen" class="tab-item" :class="{ active: route.path === '/m/screen' }">
      <div class="tab-icon-wrap">
        <svg class="tab-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
        </svg>
      </div>
      <span class="tab-label">选股</span>
    </router-link>

    <router-link to="/m/watchlist" class="tab-item" :class="{ active: route.path === '/m/watchlist' }">
      <div class="tab-icon-wrap">
        <svg class="tab-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
        </svg>
        <span v-if="watchCount > 0" class="tab-badge">{{ watchCount > 99 ? '99+' : watchCount }}</span>
      </div>
      <span class="tab-label">自选</span>
    </router-link>
  </nav>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useWatchlistStore } from '@/stores/watchlist'

const route = useRoute()
const wlStore = useWatchlistStore()

const watchCount = computed(() => wlStore.stocks.length)

onMounted(() => {
  wlStore.fetchWatchlist()
})
</script>

<style scoped>
.tab-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 100;
  display: flex;
  align-items: stretch;
  background: linear-gradient(180deg, rgba(11, 15, 20, 0.92) 0%, rgba(11, 15, 20, 0.98) 100%);
  backdrop-filter: blur(16px) saturate(1.2);
  -webkit-backdrop-filter: blur(16px) saturate(1.2);
  border-top: 1px solid var(--border);
  padding-bottom: env(safe-area-inset-bottom, 0px);
  height: calc(var(--tabbar-height) + env(safe-area-inset-bottom, 0px));
}

.tab-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  text-decoration: none;
  color: var(--text-muted);
  transition: color 0.15s ease;
  padding: 8px 0;
  min-height: 44px;
}

.tab-item:active {
  background: rgba(255, 255, 255, 0.04);
}

.tab-item.active {
  color: var(--accent-cyan);
}

.tab-icon-wrap {
  position: relative;
  flex-shrink: 0;
}

.tab-icon {
  display: block;
}

.tab-badge {
  position: absolute;
  top: -4px;
  right: -8px;
  min-width: 16px;
  height: 16px;
  background: var(--accent-red);
  color: #fff;
  font-size: 0.6rem;
  font-weight: 700;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
  box-shadow: 0 2px 6px rgba(239, 68, 68, 0.5);
}

.tab-label {
  font-size: 0.65rem;
  font-weight: 600;
}
</style>
