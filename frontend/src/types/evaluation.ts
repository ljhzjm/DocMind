// Vue 概念：类型定义让评测配置、请求和指标结果在组件中保持强类型。
// Vue 概念：配置数组由 v-for 渲染，用户可以增删不同检索方案。
// Vue 概念：结果表与样本明细复用同一份响应式数据。

export type SearchMode = 'vector' | 'bm25' | 'hybrid'

export interface EvalDatasetSummary {
  dataset_name: string
  case_count: number
}

export interface RetrievalConfigInput {
  name: string
  mode: SearchMode
  top_k: number
  rerank: boolean
}

export interface EvalRunRequest {
  dataset_name: string
  configs: RetrievalConfigInput[]
}

export interface CaseMetrics {
  question: string
  recall_at_5: number
  reciprocal_rank: number
  faithfulness: number
  answer_relevance: number
  ragas_faithfulness: number | null
  ragas_answer_relevance: number | null
  latency_ms: number
  estimated_cost: number
  error: string | null
}

export interface ConfigMetrics extends RetrievalConfigInput {
  case_count: number
  recall_at_5: number
  mrr: number
  faithfulness: number
  answer_relevance: number
  ragas_faithfulness: number | null
  ragas_answer_relevance: number | null
  average_latency_ms: number
  average_estimated_cost: number
  cases: CaseMetrics[]
}

export interface EvalRunResponse {
  dataset_name: string
  results: ConfigMetrics[]
}
