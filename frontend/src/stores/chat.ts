// Vue 概念：Pinia store 使用 ref/computed 保存跨组件共享状态。
// Vue 概念：action 中统一处理异步请求，组件不需要直接管理请求细节。
// Vue 概念：AbortController 让组件通过 store action 安全停止流式生成。

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { streamChat } from '../api/chatStream'
import type { ChatMessage, ChatSession } from '../types/chat'

export type ChatStatus =
  'idle' | 'streaming' | 'completed' | 'stopped' | 'error'

function createId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
}

function createSession(): ChatSession {
  return {
    id: createId(),
    title: '新会话',
    messages: [],
  }
}

function createAssistantMessage(): ChatMessage {
  return {
    id: createId(),
    role: 'assistant',
    content: '',
    citations: [],
    contexts: [],
    error: '',
    streaming: true,
  }
}

export const useChatStore = defineStore('chat', () => {
  const sessions = ref<ChatSession[]>([createSession()])
  const activeSessionId = ref(sessions.value[0]?.id ?? '')
  const query = ref('')
  const status = ref<ChatStatus>('idle')
  const retrievalSummary = ref('')
  let activeController: AbortController | null = null

  const activeSession = computed(
    () =>
      sessions.value.find((session) => session.id === activeSessionId.value) ??
      sessions.value[0],
  )
  const isStreaming = computed(() => status.value === 'streaming')
  const canSend = computed(
    () => query.value.trim().length > 0 && !isStreaming.value,
  )

  function newSession(): void {
    if (isStreaming.value) {
      stop()
    }
    const session = createSession()
    sessions.value.unshift(session)
    activeSessionId.value = session.id
    resetInput()
  }

  function selectSession(sessionId: string): void {
    if (isStreaming.value) {
      stop()
    }
    activeSessionId.value = sessionId
    resetInput()
  }

  function deleteSession(sessionId: string): void {
    if (isStreaming.value) {
      stop()
    }
    sessions.value = sessions.value.filter(
      (session) => session.id !== sessionId,
    )
    if (sessions.value.length === 0) {
      sessions.value.push(createSession())
    }
    if (activeSessionId.value === sessionId) {
      activeSessionId.value = sessions.value[0]?.id ?? ''
    }
  }

  async function send(): Promise<void> {
    const currentQuery = query.value.trim()
    const session = activeSession.value
    if (
      currentQuery.length === 0 ||
      isStreaming.value ||
      session === undefined
    ) {
      return
    }

    if (session.messages.length === 0) {
      session.title = currentQuery.slice(0, 24)
    }
    session.messages.push({
      id: createId(),
      role: 'user',
      content: currentQuery,
      citations: [],
      contexts: [],
      error: '',
      streaming: false,
    })
    const assistant = createAssistantMessage()
    session.messages.push(assistant)
    query.value = ''
    retrievalSummary.value = ''
    status.value = 'streaming'
    activeController = new AbortController()

    try {
      await streamChat(currentQuery, activeController.signal, {
        onRetrieval(event) {
          assistant.contexts = event.contexts
          retrievalSummary.value = `检索完成：${event.chunk_count} 个片段，${event.latency_ms.toFixed(1)} ms`
        },
        onAnswer(event) {
          assistant.content += event.delta
        },
        onDone(event) {
          assistant.citations = event.citations
          assistant.streaming = false
          status.value = 'completed'
        },
        onError(event) {
          assistant.error = event.message
          assistant.streaming = false
          status.value = 'error'
        },
      })
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        assistant.streaming = false
        status.value = 'stopped'
      } else {
        assistant.error = error instanceof Error ? error.message : '请求失败'
        assistant.streaming = false
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

  function resetInput(): void {
    query.value = ''
    status.value = 'idle'
    retrievalSummary.value = ''
  }

  return {
    sessions,
    activeSessionId,
    activeSession,
    query,
    status,
    retrievalSummary,
    isStreaming,
    canSend,
    send,
    stop,
    newSession,
    selectSession,
    deleteSession,
  }
})
