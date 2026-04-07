<template>
  <nav class="tab-bar">
    <router-link to="/m" class="tab-item" :class="{ active: route.path === '/m' }" :exact="true">
      <svg class="tab-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
        <polyline points="9 22 9 12 15 12 15 22"/>
      </svg>
      <span class="tab-label">首页</span>
    </router-link>

    <router-link to="/m/screen" class="tab-item" :class="{ active: route.path === '/m/screen' }">
      <svg class="tab-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
      </svg>
      <span class="tab-label">选股</span>
    </router-link>

    <router-link to="/m/watchlist" class="tab-item" :class="{ active: route.path === '/m/watchlist' }">
      <svg class="tab-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z"/>
        <path d="M12 6v6l4 2"/>
      </svg>
      <span class="tab-label">自选</span>
    </router-link>
  </nav>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
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

.tab-icon {
  flex-shrink: 0;
}

.tab-label {
  font-size: 0.65rem;
  font-weight: 600;
}
</style>
