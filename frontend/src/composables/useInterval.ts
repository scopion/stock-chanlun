/**
 * 定时器 Hook - 自动清理
 */
import { ref, onUnmounted } from 'vue'

export function useInterval(callback: () => void, delay: number | null) {
  const isActive = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  function start() {
    if (timer) clearInterval(timer)
    if (delay === null || delay <= 0) return
    isActive.value = true
    timer = setInterval(callback, delay)
  }

  function stop() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
    isActive.value = false
  }

  function restart(newDelay?: number) {
    stop()
    if (newDelay !== undefined) {
      startWithDelay(newDelay)
    } else if (delay !== null && delay > 0) {
      start()
    }
  }

  function startWithDelay(newDelay: number) {
    if (timer) clearInterval(timer)
    if (newDelay <= 0) return
    isActive.value = true
    timer = setInterval(callback, newDelay)
  }

  onUnmounted(() => {
    stop()
  })

  // Auto-start
  if (delay !== null && delay > 0) {
    start()
  }

  return { isActive, start, stop, restart }
}

/**
 * 延迟执行 Hook
 */
export function useTimeout(callback: () => void, delay: number | null) {
  const isPending = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null

  function start() {
    if (timer) clearTimeout(timer)
    if (delay === null || delay <= 0) return
    isPending.value = true
    timer = setTimeout(() => {
      callback()
      isPending.value = false
    }, delay)
  }

  function cancel() {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    isPending.value = false
  }

  onUnmounted(() => {
    cancel()
  })

  return { isPending, start, cancel }
}

/**
 * 响应式时间（自动更新）
 */
import { computed } from 'vue'

export function useNow(interval = 1000) {
  const now = ref(Date.now())

  const { start, stop } = useInterval(() => {
    now.value = Date.now()
  }, interval)

  start()

  const formatted = computed(() => {
    const d = new Date(now.value)
    return d.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  })

  const date = computed(() => {
    const d = new Date(now.value)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  })

  onUnmounted(stop)

  return { now, formatted, date }
}