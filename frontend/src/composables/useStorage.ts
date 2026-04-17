/**
 * 本地存储 Hook - 支持响应式和 JSON 自动序列化
 */
import { ref, watch } from 'vue'

export function useStorage<T>(key: string, defaultValue: T): [Ref<T>, (value: T) => void] {
  const stored = localStorage.getItem(key)
  const initial = stored ? (JSON.parse(stored) as T) : defaultValue
  const value = ref<T>(initial) as Ref<T>

  function setItem(newValue: T) {
    value.value = newValue
    localStorage.setItem(key, JSON.stringify(newValue))
  }

  watch(value, (newVal) => {
    localStorage.setItem(key, JSON.stringify(newVal))
  }, { deep: true })

  return [value, setItem]
}

/**
 * Session Storage 版本
 */
export function useSessionStorage<T>(key: string, defaultValue: T): [Ref<T>, (value: T) => void] {
  const stored = sessionStorage.getItem(key)
  const initial = stored ? (JSON.parse(stored) as T) : defaultValue
  const value = ref<T>(initial) as Ref<T>

  function setItem(newValue: T) {
    value.value = newValue
    sessionStorage.setItem(key, JSON.stringify(newValue))
  }

  watch(value, (newVal) => {
    sessionStorage.setItem(key, JSON.stringify(newVal))
  }, { deep: true })

  return [value, setItem]
}