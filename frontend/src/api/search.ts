// Vue 概念：API 函数接收明确参数并返回类型化 Promise。
// Vue 概念：URLSearchParams 负责安全编码查询参数和中文内容。
// Vue 概念：调试页面只需处理成功数据或 Error，不接触底层响应细节。

import type { SearchDebugTrace } from '../types/search'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(
  /\/$/,
  '',
)
const SEARCH_DEBUG_URL = `${API_BASE_URL}/api/v1/search/debug`

export async function fetchSearchDebug(
  query: string,
  topK: number,
): Promise<SearchDebugTrace> {
  const params = new URLSearchParams({
    q: query,
    top_k: String(topK),
  })
  const response = await fetch(`${SEARCH_DEBUG_URL}?${params.toString()}`)
  if (!response.ok) {
    throw new Error(`检索调试请求失败：${response.status}`)
  }
  return (await response.json()) as SearchDebugTrace
}
