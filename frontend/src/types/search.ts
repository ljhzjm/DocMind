// Vue 概念：接口类型描述后端 debug trace，模板可以按步骤读取字段。
// Vue 概念：联合类型限制检索来源，避免出现任意字符串。
// Vue 概念：明确的响应类型让调试页面更容易维护和重构。

export type RetrievalSource = 'vector' | 'bm25'

export interface SearchResult {
  chunk_id: string
  document_id: string
  content: string
  document_name: string
  page_number: number | null
  heading_path: string[]
  score: number
  sources: RetrievalSource[]
}

export interface SearchStep {
  latency_ms: number
  error: string | null
  results: SearchResult[]
}

export interface RewriteTrace {
  query: string
  keywords: string[]
  retrieval_query: string
  latency_ms: number
}

export interface SearchDebugTrace {
  query: string
  top_k: number
  rewrite: RewriteTrace
  vector: SearchStep
  bm25: SearchStep
  fusion: SearchStep
  rerank: SearchStep
}
