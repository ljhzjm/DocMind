// Vue 概念：API 模块封装会话列表、创建和历史消息加载。
// Vue 概念：所有响应均使用明确 TS 类型，方便 store 恢复状态。
// Vue 概念：组件不直接拼接后端 URL。

import type {
  ConversationItem,
  ConversationMessage,
} from '../types/conversation'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(
  /\/$/,
  '',
)
const CONVERSATIONS_URL = `${API_BASE_URL}/api/v1/conversations`

export async function fetchConversations(): Promise<ConversationItem[]> {
  const response = await fetch(CONVERSATIONS_URL)
  if (!response.ok) {
    throw new Error(`会话列表请求失败：${response.status}`)
  }
  return (await response.json()) as ConversationItem[]
}

export async function createConversation(
  title: string,
): Promise<ConversationItem> {
  const response = await fetch(CONVERSATIONS_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  if (!response.ok) {
    throw new Error(`创建会话失败：${response.status}`)
  }
  return (await response.json()) as ConversationItem
}

export async function fetchConversationMessages(
  conversationId: string,
): Promise<ConversationMessage[]> {
  const response = await fetch(
    `${CONVERSATIONS_URL}/${conversationId}/messages`,
  )
  if (!response.ok) {
    throw new Error(`历史消息请求失败：${response.status}`)
  }
  return (await response.json()) as ConversationMessage[]
}
