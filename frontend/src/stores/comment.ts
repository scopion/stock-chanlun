import { defineStore } from 'pinia'
import { ref } from 'vue'
import { stockApi } from '../api/stock'
import type { Comment } from '../api/stock'

export const useCommentStore = defineStore('comment', () => {
  // key: stockCode, value: comment list
  const cache = ref<Record<string, Comment[]>>({})
  const loadingMap = ref<Record<string, boolean>>({})
  const errorMap = ref<Record<string, string>>({})

  async function fetchComments(code: string) {
    if (loadingMap.value[code]) return
    loadingMap.value[code] = true
    errorMap.value[code] = ''
    try {
      const res = await stockApi.getComments(code)
      cache.value[code] = res.data.comments ?? []
    } catch (e: unknown) {
      errorMap.value[code] = (e as Error).message ?? '加载失败'
    } finally {
      loadingMap.value[code] = false
    }
  }

  async function addComment(code: string, content: string): Promise<Comment> {
    const res = await stockApi.addComment(code, content)
    if (!cache.value[code]) cache.value[code] = []
    cache.value[code].unshift(res.data.comment)
    return res.data.comment
  }

  async function updateComment(code: string, commentId: string, content: string): Promise<Comment> {
    const res = await stockApi.updateComment(code, commentId, content)
    const list = cache.value[code]
    if (list) {
      const idx = list.findIndex(c => c.id === commentId)
      if (idx >= 0) list[idx] = res.data.comment
    }
    return res.data.comment
  }

  async function deleteComment(code: string, commentId: string) {
    await stockApi.deleteComment(code, commentId)
    const list = cache.value[code]
    if (list) {
      cache.value[code] = list.filter(c => c.id !== commentId)
    }
  }

  function isLoading(code: string) { return !!loadingMap.value[code] }
  function getError(code: string) { return errorMap.value[code] ?? '' }
  function getComments(code: string): Comment[] { return cache.value[code] ?? [] }

  return { cache, fetchComments, addComment, updateComment, deleteComment, isLoading, getError, getComments }
})
