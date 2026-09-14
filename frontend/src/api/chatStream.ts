// Vue 概念：API 模块把网络请求从组件中分离，组件只调用函数并更新响应式状态。
// Vue 概念：ReadableStream 会持续产生数据，适合实现 SSE 的逐段渲染。
// Vue 概念：AbortSignal 用于让“停止生成”按钮中断正在进行的请求。

import type {
  AnswerEvent,
  ChatStreamEvent,
  ChatStreamHandlers,
  CitationContext,
  DoneEvent,
  ErrorEvent,
  RetrievalEvent,
} from '../types/chat'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(
  /\/$/,
  '',
)
const CHAT_STREAM_URL = `${API_BASE_URL}/api/chat/stream`

export async function streamChat(
  query: string,
  signal: AbortSignal,
  handlers: ChatStreamHandlers,
): Promise<void> {
  const response = await fetch(CHAT_STREAM_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ query }),
    signal,
  })

  if (!response.ok) {
    throw new Error(`SSE request failed with status ${response.status}`)
  }
  if (response.body === null) {
    throw new Error('SSE response body is unavailable')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    let finished = false
    while (!finished) {
      const { done, value } = await reader.read()
      finished = done
      buffer += decoder.decode(value, { stream: !done })

      let separatorIndex = buffer.indexOf('\n\n')
      while (separatorIndex >= 0) {
        const block = buffer.slice(0, separatorIndex)
        buffer = buffer.slice(separatorIndex + 2)
        dispatchEvent(parseSSEBlock(block), handlers)
        separatorIndex = buffer.indexOf('\n\n')
      }
    }
    dispatchEvent(parseSSEBlock(buffer), handlers)
  } finally {
    reader.releaseLock()
  }
}

export function parseSSEBlock(block: string): ChatStreamEvent | null {
  let eventName = 'message'
  const dataLines: string[] = []

  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event:')) {
      eventName = line.slice('event:'.length).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart())
    }
  }

  if (dataLines.length === 0) {
    return null
  }

  const rawData: unknown = JSON.parse(dataLines.join('\n'))
  if (!isRecord(rawData)) {
    throw new Error('SSE data must be a JSON object')
  }

  if (eventName === 'retrieval') {
    return {
      type: 'retrieval',
      latency_ms: requireNumber(rawData, 'latency_ms'),
      chunk_count: requireNumber(rawData, 'chunk_count'),
      contexts: requireCitationContexts(rawData),
    }
  }
  if (eventName === 'answer') {
    return { type: 'answer', delta: requireString(rawData, 'delta') }
  }
  if (eventName === 'done') {
    return { type: 'done', citations: requireNumberArray(rawData, 'citations') }
  }
  if (eventName === 'error') {
    return { type: 'error', message: requireString(rawData, 'message') }
  }
  return null
}

function dispatchEvent(
  event: ChatStreamEvent | null,
  handlers: ChatStreamHandlers,
): void {
  if (event === null) {
    return
  }
  if (event.type === 'retrieval') {
    handlers.onRetrieval(event)
  } else if (event.type === 'answer') {
    handlers.onAnswer(event)
  } else if (event.type === 'done') {
    handlers.onDone(event)
  } else {
    handlers.onError(event)
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requireString(record: Record<string, unknown>, key: string): string {
  const value = record[key]
  if (typeof value !== 'string') {
    throw new Error(`SSE field '${key}' must be a string`)
  }
  return value
}

function requireNumber(record: Record<string, unknown>, key: string): number {
  const value = record[key]
  if (typeof value !== 'number') {
    throw new Error(`SSE field '${key}' must be a number`)
  }
  return value
}

function requireCitationContexts(
  record: Record<string, unknown>,
): CitationContext[] {
  const value = record.contexts
  if (!Array.isArray(value)) {
    return []
  }
  return value.map((item) => {
    if (!isRecord(item)) {
      throw new Error('SSE citation context must be an object')
    }
    return {
      citation_number: requireNumber(item, 'citation_number'),
      chunk_id: requireString(item, 'chunk_id'),
      content: requireString(item, 'content'),
      document_name: requireString(item, 'document_name'),
      page_number:
        item.page_number === null ? null : requireNumber(item, 'page_number'),
      heading_path: requireStringArray(item, 'heading_path'),
      score: requireNumber(item, 'score'),
    }
  })
}

function requireStringArray(
  record: Record<string, unknown>,
  key: string,
): string[] {
  const value = record[key]
  if (
    !Array.isArray(value) ||
    !value.every((item) => typeof item === 'string')
  ) {
    throw new Error(`SSE field '${key}' must be a string array`)
  }
  return value
}

function requireNumberArray(
  record: Record<string, unknown>,
  key: string,
): number[] {
  const value = record[key]
  if (
    !Array.isArray(value) ||
    !value.every((item) => typeof item === 'number')
  ) {
    throw new Error(`SSE field '${key}' must be a number array`)
  }
  return value
}

export type {
  AnswerEvent,
  ChatStreamEvent,
  DoneEvent,
  ErrorEvent,
  RetrievalEvent,
}
