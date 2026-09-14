// Vue 概念：API 模块集中处理评测请求，组件只维护界面状态。
// Vue 概念：POST 请求体使用明确的 TypeScript 结构，避免临时拼装对象。
// Vue 概念：返回的指标结果直接驱动对比表重新渲染。

import type {
  EvalDatasetSummary,
  EvalRunRequest,
  EvalRunResponse,
  EvaluationRunSummary,
} from '../types/evaluation'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(
  /\/$/,
  '',
)
const EVAL_URL = `${API_BASE_URL}/api/v1/eval`

export async function fetchEvalDatasets(): Promise<EvalDatasetSummary[]> {
  const response = await fetch(`${EVAL_URL}/datasets`)
  if (!response.ok) {
    throw new Error(`数据集请求失败：${response.status}`)
  }
  return (await response.json()) as EvalDatasetSummary[]
}

export async function runEvaluation(
  request: EvalRunRequest,
): Promise<EvalRunResponse> {
  const response = await fetch(`${EVAL_URL}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    throw new Error(`评测运行失败：${response.status}`)
  }
  return (await response.json()) as EvalRunResponse
}
export async function fetchEvaluationRuns(): Promise<EvaluationRunSummary[]> {
  const response = await fetch(`${EVAL_URL}/runs`)
  if (!response.ok) {
    throw new Error(`评测历史请求失败：${response.status}`)
  }
  return (await response.json()) as EvaluationRunSummary[]
}

export async function fetchEvaluationRun(
  runId: string,
): Promise<EvalRunResponse> {
  const response = await fetch(`${EVAL_URL}/runs/${runId}`)
  if (!response.ok) {
    throw new Error(`评测记录请求失败：${response.status}`)
  }
  return (await response.json()) as EvalRunResponse
}
