/**
 * 全局 Loading 状态管理
 */
import { ref, computed } from 'vue'

type LoadingKey = 'global' | 'kline' | 'chanlun' | 'ai' | 'watchlist'

const loadings = ref<Record<LoadingKey, boolean>>({
  global: false,
  kline: false,
  chanlun: false,
  ai: false,
  watchlist: false,
})

export function useLoading() {
  /** 设置某个 loading 状态 */
  function setLoading(key: LoadingKey, value: boolean) {
    loadings.value[key] = value
  }

  /** 是否有任何 loading 状态 */
  const isAnyLoading = computed(() => Object.values(loadings.value).some(v => v))

  /** 获取指定 key 的 loading 状态 */
  function isLoading(key: LoadingKey): boolean {
    return loadings.value[key]
  }

  /** 清除所有 loading 状态 */
  function clearAll() {
    for (const key in loadings.value) {
      loadings.value[key as LoadingKey] = false
    }
  }

  return {
    loadings,
    isAnyLoading,
    isLoading,
    setLoading,
    clearAll,
  }
}

// 全局单例
export const globalLoading = useLoading()