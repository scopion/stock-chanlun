<template>
  <header class="search-bar">
    <div class="search-inner">
      <div class="search-input-wrap">
        <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
        </svg>
        <input
          v-model="keyword"
          @keydown.enter="doSearch"
          placeholder="输入股票代码或名称"
          class="search-input"
          autocomplete="off"
          autocorrect="off"
          spellcheck="false"
        />
        <button v-if="keyword" class="search-clear" @click="keyword = ''" aria-label="清除">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M18 6 6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- 搜索结果下拉 -->
    <div v-if="results.length > 0" class="search-results">
      <button
        v-for="s in results"
        :key="s.code"
        class="search-result-item"
        @click="select(s.code)"
      >
        <span class="sri-code mono">{{ s.code }}</span>
        <span class="sri-name">{{ s.name }}</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="m9 18 6-6-6-6"/>
        </svg>
      </button>
    </div>
    <!-- 搜索中 -->
    <div v-if="searching" class="search-loading">
      <div class="mini-spinner" />
      <span>搜索中...</span>
    </div>
    <div v-else-if="searched && results.length === 0" class="search-empty">
      未找到「{{ keyword }}」相关股票
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { stockApi } from '@/api/stock'

const emit = defineEmits<{ search: [code: string] }>()

const keyword = ref('')
const results = ref<{ code: string; name: string }[]>([])
const searched = ref(false)
const searching = ref(false)

async function doSearch() {
  if (!keyword.value.trim()) return
  searching.value = true
  searched.value = false
  results.value = []
  try {
    const res = await stockApi.search(keyword.value.trim())
    results.value = res.data.stocks ?? []
  } catch {
    results.value = []
  } finally {
    searched.value = true
    searching.value = false
  }
}

function select(code: string) {
  results.value = []
  keyword.value = ''
  searched.value = false
  emit('search', code)
}
</script>

<style scoped>
.search-bar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: linear-gradient(180deg, rgba(11, 15, 20, 0.95) 0%, rgba(11, 15, 20, 0.88) 100%);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  padding: 10px 16px;
  padding-top: calc(10px + env(safe-area-inset-top, 0px));
}

.search-inner {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-input-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0 12px;
  height: 40px;
  transition: border-color 0.15s;
}

.search-input-wrap:focus-within {
  border-color: var(--accent-blue);
}

.search-icon {
  flex-shrink: 0;
  color: var(--text-muted);
}

.search-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: 0.9rem;
  font-family: var(--font-sans);
}

.search-input::placeholder {
  color: var(--text-muted);
}

.search-clear {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: color 0.15s;
}

.search-clear:hover {
  color: var(--text-primary);
}

/* 搜索结果 */
.search-results {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: var(--bg-card);
  border: 1px solid var(--border-strong);
  border-top: none;
  border-radius: 0 0 12px 12px;
  overflow: hidden;
  box-shadow: var(--shadow-md);
  z-index: 99;
}

.search-result-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--divider);
  color: inherit;
  font: inherit;
  cursor: pointer;
  width: 100%;
  text-align: left;
  transition: background 0.12s;
  min-height: 44px;
}

.search-result-item:last-child {
  border-bottom: none;
}

.search-result-item:active {
  background: var(--bg-hover);
}

.sri-code {
  font-size: 0.85rem;
  color: var(--accent-blue);
  min-width: 80px;
}

.sri-name {
  flex: 1;
  font-size: 0.9rem;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-result-item svg {
  color: var(--text-muted);
  flex-shrink: 0;
}

.search-empty {
  padding: 14px 16px;
  font-size: 0.85rem;
  color: var(--text-muted);
  background: var(--bg-card);
  border: 1px solid var(--border-strong);
  border-top: none;
  border-radius: 0 0 12px 12px;
}

.search-loading {
  padding: 14px 16px;
  font-size: 0.85rem;
  color: var(--text-muted);
  background: var(--bg-card);
  border: 1px solid var(--border-strong);
  border-top: none;
  border-radius: 0 0 12px 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.mini-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--accent-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
