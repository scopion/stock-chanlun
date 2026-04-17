/**
 * 防抖 Hook
 */
import { ref, watch, onUnmounted } from 'vue'
import type { Ref } from 'vue'

export function useDebounce<T>(value: Ref<T>, delay = 300): Ref<T> {
  const debouncedValue = ref(value.value) as Ref<T>
  let timer: ReturnType<typeof setTimeout> | null = null

  watch(value, (newVal) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      debouncedValue.value = newVal
    }, delay)
  })

  onUnmounted(() => {
    if (timer) clearTimeout(timer)
  })

  return debouncedValue
}

/**
 * 防抖函数（适用于函数调用）
 */
export function useDebouncedCallback<T extends (...args: any[]) => any>(
  fn: T,
  delay = 300
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout> | null = null

  return (...args: Parameters<T>) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      fn(...args)
    }, delay)
  }
}

/**
 * 节流 Hook
 */
export function useThrottle<T>(value: Ref<T>, delay = 300): Ref<T> {
  const throttledValue = ref(value.value) as Ref<T>
  let lastTime = 0

  watch(value, (newVal) => {
    const now = Date.now()
    if (now - lastTime >= delay) {
      throttledValue.value = newVal
      lastTime = now
    }
  })

  return throttledValue
}

/**
 * 节流函数（适用于函数调用）
 */
export function useThrottledCallback<T extends (...args: any[]) => any>(
  fn: T,
  delay = 300
): (...args: Parameters<T>) => void {
  let lastTime = 0
  let timer: ReturnType<typeof setTimeout> | null = null

  return (...args: Parameters<T>) => {
    const now = Date.now()
    if (now - lastTime >= delay) {
      lastTime = now
      fn(...args)
    } else {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        lastTime = Date.now()
        fn(...args)
      }, delay - (now - lastTime))
    }
  }
}