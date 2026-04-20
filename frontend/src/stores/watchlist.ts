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
    if (stocks.value.some(s => s.code === code)) {
      const err = new Error('该股票已在自选列表中')
      error.value = err.message
      throw err
    }
    try {
      await stockApi.addWatch(code)
      await fetchWatchlist()
    } catch (e: any) {
      error.value = e.message
      throw e
    }
  }

  async function removeStock(code: string) {
    const snapshot = [...stocks.value]
    stocks.value = stocks.value.filter(s => s.code !== code)
    try {
      await stockApi.removeWatch(code)
    } catch (e: any) {
      stocks.value = snapshot
      error.value = e.message
      throw e
    }
  }

  return { stocks, loading, error, lastUpdated, sortedByChange, hasSignals,
           fetchWatchlist, addStock, removeStock }
})