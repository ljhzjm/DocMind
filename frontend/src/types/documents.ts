// Vue 概念：文档状态使用联合类型，模板可以根据状态安全显示不同标签。
// Vue 概念：接口字段与后端响应保持一致，避免组件中猜测数据结构。
// Vue 概念：切片类型用于抽屉组件展示页码、标题路径和原文。

export type DocumentStatus = 'uploaded' | 'parsing' | 'ready' | 'failed'

export interface DocumentItem {
  document_id: string
  filename: string
  status: DocumentStatus
  file_type: string
  file_size: number
  chunk_count: number
  created_at: string
}

export interface DocumentChunk {
  chunk_id: string
  chunk_index: number
  content: string
  page_number: number | null
  heading_path: string[]
}

export interface DocumentUploadResponse {
  document_id: string
  task_id: string
  status: DocumentStatus
}

export interface DocumentStatusResponse {
  document_id: string
  filename: string
  status: DocumentStatus
  chunk_count: number
}
export interface EmbeddingTaskResponse {
  document_id: string
  task_id: string
  status: DocumentStatus
}
