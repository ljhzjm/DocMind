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
    traceId: null,
    cached: false,
  }
}

interface StreamRenderer {
  push: (delta: string) => void
  complete: (citations: number[]) => void
  fail: (message: string) => void
  cancel: () => void
}

function createStreamRenderer(
  assistant: ChatMessage,
  onComplete: () => void,
  onFailure: () => void,
): StreamRenderer {
  let pending = ''
  let completedCitations: number[] | null = null
  let failureMessage: string | null = null
  let cancelled = false
  const timer = globalThis.setInterval(() => {
    if (cancelled) {
      return
    }

    if (pending.length > 0) {
      // 每次最多显示 2 个字符，避免上游 token 突发时整段一次性渲染。
      const step = 2
      assistant.content += pending.slice(0, step)
      pending = pending.slice(step)
      return
    }

    if (completedCitations !== null) {
      assistant.citations = completedCitations
      assistant.streaming = false
      globalThis.clearInterval(timer)
      onComplete()
      return
    }

    if (failureMessage !== null) {
      assistant.error = failureMessage
      assistant.streaming = false
      globalThis.clearInterval(timer)
      onFailure()
    }
  }, 16)

  return {
    push(delta) {
      pending += delta
    },
    complete(citations) {
      completedCitations = citations
    },
    fail(message) {
      failureMessage = message
    },
    cancel() {
      cancelled = true
      globalThis.clearInterval(timer)
    },
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
      traceId: null,
      cached: false,
    })
    session.messages.push(createAssistantMessage())
    const assistant = session.messages[session.messages.length - 1]
    if (assistant === undefined) {
      return
    }
    query.value = ''
    retrievalSummary.value = ''
    status.value = 'streaming'
    activeController = new AbortController()

    const renderer = createStreamRenderer(
      assistant,
      () => {
        status.value = 'completed'
      },
      () => {
        status.value = 'error'
      },
    )

    try {
      await streamChat(currentQuery, activeController.signal, {
        onRetrieval(event) {
          assistant.contexts = event.contexts
          assistant.traceId = event.trace_id
          assistant.cached = event.cached
          retrievalSummary.value = `检索完成：${event.chunk_count} 个片段，${event.latency_ms.toFixed(1)} ms`
        },
        onAnswer(event) {
          renderer.push(event.delta)
        },
        onDone(event) {
          assistant.traceId = event.trace_id
          renderer.complete(event.citations)
        },
        onError(event) {
          renderer.fail(event.message)
        },
      })
    } catch (error: unknown) {
      renderer.cancel()
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
