import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { stockApi, type Quote } from '../api/stock'

export const useWatchlistStore = defineStore('watchlist', () => {
  const stocks = ref<Quote[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastUpdated = ref<Date | null>(null)

  const sortedByChange = computed(() =>
    [...stocks.value].sort((a, b) => b.change_pct - a.change_pct)
  )

  const hasSignals = computed(() =>
    stocks.value.some(s => s.change_pct > 0)
  )

  async function fetchWatchlist() {
    loading.value = true
    error.value = null
    try {
      const res = await stockApi.watchlist()
      stocks.value = res.data.stocks || []
      lastUpdated.value = new Date()
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function addStock(code: string) {
    try {
      await stockApi.addWatch(code)
      await fetchWatchlist()
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function removeStock(code: string) {
    try {
      await stockApi.removeWatch(code)
      stocks.value = stocks.value.filter(s => s.code !== code)
    } catch (e: any) {
      error.value = e.message
    }
  }

  return { stocks, loading, error, lastUpdated, sortedByChange, hasSignals,
           fetchWatchlist, addStock, removeStock }
})