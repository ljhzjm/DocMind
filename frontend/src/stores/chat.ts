// Vue 概念：Pinia store 使用 ref/computed 保存跨组件共享状态。
// Vue 概念：action 中统一处理异步请求，组件不需要直接管理请求细节。
// Vue 概念：AbortController 让组件通过 store action 安全停止流式生成。

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { streamChat } from '../api/chatStream'

export type ChatStatus =
  'idle' | 'streaming' | 'completed' | 'stopped' | 'error'

export const useChatStore = defineStore('chat', () => {
  const query = ref('')
  const answer = ref('')
  const status = ref<ChatStatus>('idle')
  const errorMessage = ref('')
  const retrievalSummary = ref('')
  let activeController: AbortController | null = null

  const isStreaming = computed(() => status.value === 'streaming')
  const canSend = computed(
    () => query.value.trim().length > 0 && !isStreaming.value,
  )

  async function send(): Promise<void> {
    const currentQuery = query.value.trim()
    if (currentQuery.length === 0 || isStreaming.value) {
      return
    }

    answer.value = ''
    errorMessage.value = ''
    retrievalSummary.value = ''
    status.value = 'streaming'
    activeController = new AbortController()

    try {
      await streamChat(currentQuery, activeController.signal, {
        onRetrieval(event) {
          retrievalSummary.value = `检索完成：${event.chunk_count} 个片段，${event.latency_ms.toFixed(1)} ms`
        },
        onAnswer(event) {
          answer.value += event.delta
        },
        onDone() {
          status.value = 'completed'
        },
        onError(event) {
          errorMessage.value = event.message
          status.value = 'error'
        },
      })
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        status.value = 'stopped'
      } else {
        errorMessage.value = error instanceof Error ? error.message : '请求失败'
        status.value = 'error'
      }
    } finally {
      activeController = null
    }
  }

  function stop(): void {
    if (activeController === null) {
      return
    }
    activeController.abort()
    status.value = 'stopped'
  }

  return {
    query,
    answer,
    status,
    errorMessage,
    retrievalSummary,
    isStreaming,
    canSend,
    send,
    stop,
  }
})
