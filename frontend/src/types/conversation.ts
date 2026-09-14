// Vue 概念：会话类型描述后端持久化数据，Pinia 用它恢复历史消息。
// Vue 概念：消息角色用联合类型限制，避免模板出现未知状态。
// Vue 概念：API 返回结构与前端 store 保持一一对应。

export interface ConversationItem {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations: Array<Record<string, unknown>> | null
  created_at: string
}
