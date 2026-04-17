/**
 * 剪贴板 Hook - 支持复制文本到剪贴板
 */
import { ref } from 'vue'

export function useClipboard() {
  const copied = ref(false)
  const error = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null

  async function copy(text: string): Promise<boolean> {
    error.value = null
    copied.value = false

    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text)
      } else {
        // Fallback for older browsers
        const textarea = document.createElement('textarea')
        textarea.value = text
        textarea.style.position = 'fixed'
        textarea.style.left = '-9999px'
        textarea.style.top = '-9999px'
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand('copy')
        document.body.removeChild(textarea)
      }

      copied.value = true
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => { copied.value = false }, 2000)
      return true
    } catch (e) {
      error.value = '复制失败'
      return false
    }
  }

  return { copy, copied, error }
}