// Vue 概念：Pinia store 使用 ref/computed 保存跨组件共享状态。
// Vue 概念：action 中统一处理异步请求，组件不需要直接管理请求细节。
// Vue 概念：AbortController 让组件通过 store action 安全停止流式生成。

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { streamChat } from '../api/chatStream'
import {
  createConversation,
  fetchConversationMessages,
  fetchConversations,
} from '../api/conversations'
import type { ConversationMessage } from '../types/conversation'
import type { ChatMessage, ChatSession, CitationContext } from '../types/chat'

export type ChatStatus =
  'idle' | 'streaming' | 'completed' | 'stopped' | 'error'

function createId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
}

function createSession(): ChatSession {
  return {
    id: `local-${createId()}`,
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
  const loadedSessionIds = new Set<string>()

  const activeSession = computed(
    () =>
      sessions.value.find((session) => session.id === activeSessionId.value) ??
      sessions.value[0],
  )
  const isStreaming = computed(() => status.value === 'streaming')
  const canSend = computed(
    () => query.value.trim().length > 0 && !isStreaming.value,
  )

  async function loadSessions(): Promise<void> {
    try {
      const stored = await fetchConversations()
      if (stored.length === 0) {
        return
      }
      sessions.value = stored.map((conversation) => ({
        id: conversation.id,
        title: conversation.title,
        messages: [],
      }))
      activeSessionId.value = sessions.value[0]?.id ?? ''
      await selectSession(activeSessionId.value)
    } catch {
      // 会话接口暂时不可用时保留当前本地会话，不阻塞聊天主流程。
    }
  }

  async function newSession(): Promise<void> {
    if (isStreaming.value) {
      stop()
    }
    const conversation = await createConversation('新会话')
    const session: ChatSession = {
      id: conversation.id,
      title: conversation.title,
      messages: [],
    }
    sessions.value.unshift(session)
    activeSessionId.value = session.id
    loadedSessionIds.add(session.id)
    resetInput()
  }

  async function selectSession(sessionId: string): Promise<void> {
    if (isStreaming.value) {
      stop()
    }
    activeSessionId.value = sessionId
    resetInput()
    if (loadedSessionIds.has(sessionId) || sessionId.startsWith('local-')) {
      return
    }
    const storedMessages = await fetchConversationMessages(sessionId)
    const session = sessions.value.find((item) => item.id === sessionId)
    if (session !== undefined) {
      session.messages = storedMessages.map(toChatMessage)
      loadedSessionIds.add(sessionId)
    }
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
      if (session.id.startsWith('local-')) {
        const conversation = await createConversation(currentQuery.slice(0, 24))
        const previousId = session.id
        session.id = conversation.id
        session.title = conversation.title
        loadedSessionIds.delete(previousId)
        loadedSessionIds.add(session.id)
        activeSessionId.value = session.id
      } else {
        session.title = currentQuery.slice(0, 24)
      }
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
      await streamChat(
        currentQuery,
        activeController.signal,
        {
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
        },
        { conversationId: session.id },
      )
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
    loadSessions,
    newSession,
    selectSession,
    deleteSession,
  }
})
function toChatMessage(message: ConversationMessage): ChatMessage {
  const citations = (message.citations ?? [])
    .map((item) => Number(item.citation_number))
    .filter((value) => Number.isInteger(value))
  const contexts: CitationContext[] = (message.citations ?? []).map((item) => ({
    citation_number: Number(item.citation_number),
    chunk_id: String(item.chunk_id ?? ''),
    content: String(item.content ?? ''),
    document_name: String(item.document_name ?? ''),
    page_number: typeof item.page_number === 'number' ? item.page_number : null,
    heading_path: Array.isArray(item.heading_path)
      ? item.heading_path.map(String)
      : [],
    score: typeof item.score === 'number' ? item.score : 0,
  }))
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    citations,
    contexts,
    error: '',
    streaming: false,
    traceId: null,
    cached: false,
  }
}
