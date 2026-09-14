// Vue 概念：TypeScript 接口用于约束组件和 Pinia store 之间传递的数据。
// Vue 概念：联合类型用于区分 SSE 的不同事件，模板可以根据状态安全渲染。
// Vue 概念：明确的数据类型能避免初学者在响应式数据中出现隐式 any。

export interface CitationContext {
  citation_number: number
  chunk_id: string
  content: string
  document_name: string
  page_number: number | null
  heading_path: string[]
  score: number
}

export interface RetrievalEvent {
  type: 'retrieval'
  latency_ms: number
  chunk_count: number
  contexts: CitationContext[]
}

export interface AnswerEvent {
  type: 'answer'
  delta: string
}

export interface DoneEvent {
  type: 'done'
  citations: number[]
}

export interface ErrorEvent {
  type: 'error'
  message: string
}

export type ChatStreamEvent =
  RetrievalEvent | AnswerEvent | DoneEvent | ErrorEvent

export interface ChatStreamHandlers {
  onRetrieval: (event: RetrievalEvent) => void
  onAnswer: (event: AnswerEvent) => void
  onDone: (event: DoneEvent) => void
  onError: (event: ErrorEvent) => void
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations: number[]
  contexts: CitationContext[]
  error: string
  streaming: boolean
}

export interface ChatSession {
  id: string
  title: string
  messages: ChatMessage[]
}
