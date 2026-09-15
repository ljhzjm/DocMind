<!-- Vue 概念：props 接收父页面传入的评测结果，组件只负责展示。 -->
<!-- Vue 概念：v-for 渲染配置行，嵌套表格展示每个样本的明细。 -->
<!-- Vue 概念：纯展示组件不持有请求状态，刷新数据由父组件控制。 -->
<script setup lang="ts">
import { ElTable, ElTableColumn, ElTag } from 'element-plus'

import type { ConfigMetrics, SearchMode } from '../types/evaluation'

defineProps<{
  results: ConfigMetrics[]
}>()

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function score(value: number): string {
  return value.toFixed(2)
}

function ragasScore(value: number | null): string {
  return value === null ? '-' : value.toFixed(3)
}

function modeLabel(mode: SearchMode): string {
  return { vector: 'Vector', bm25: 'BM25', hybrid: 'Hybrid' }[mode]
}

function ragasTagType(value: number | null): 'success' | 'info' {
  return value !== null && value >= 0.8 ? 'success' : 'info'
}
</script>

<template>
  <div v-if="results.length" class="result-table-wrap">
    <table class="result-table">
      <thead>
        <tr>
          <th>配置</th>
          <th>Recall@5</th>
          <th>MRR</th>
          <th>首字延迟</th>
          <th>平均 Token</th>
          <th>忠实度</th>
          <th>相关性</th>
          <th>拒答率</th>
          <th>幻觉风险</th>
          <th>平均延迟</th>
          <th>平均成本</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="result in results" :key="result.name">
          <tr>
            <td>
              <strong>{{ result.name }}</strong>
              <span>{{ modeLabel(result.mode) }} · top{{ result.top_k }}</span>
            </td>
            <td>{{ percent(result.recall_at_5) }}</td>
            <td>{{ score(result.mrr) }}</td>
            <td>{{ result.average_first_token_latency_ms.toFixed(1) }} ms</td>
            <td>
              {{ result.average_input_tokens.toFixed(0) }} /
              {{ result.average_output_tokens.toFixed(0) }}
            </td>
            <td>
              {{ score(result.faithfulness) }}
              <ElTag
                size="small"
                :type="ragasTagType(result.ragas_faithfulness)"
              >
                RAGAS {{ ragasScore(result.ragas_faithfulness) }}
              </ElTag>
            </td>
            <td>
              {{ score(result.answer_relevance) }}
              <ElTag
                size="small"
                :type="ragasTagType(result.ragas_answer_relevance)"
              >
                RAGAS {{ ragasScore(result.ragas_answer_relevance) }}
              </ElTag>
            </td>
            <td>{{ percent(result.refusal_rate) }}</td>
            <td>{{ percent(result.hallucination_risk) }}</td>
            <td>{{ result.average_latency_ms.toFixed(1) }} ms</td>
            <td>${{ result.average_estimated_cost.toFixed(6) }}</td>
          </tr>
          <tr class="detail-row">
            <td colspan="11">
              <ElTable :data="result.cases" size="small">
                <ElTableColumn prop="question" label="问题" min-width="260" />
                <ElTableColumn label="Recall@5" width="100">
                  <template #default="scope">
                    {{ percent(scope.row.recall_at_5) }}
                  </template>
                </ElTableColumn>
                <ElTableColumn label="RR" width="80">
                  <template #default="scope">
                    {{ score(scope.row.reciprocal_rank) }}
                  </template>
                </ElTableColumn>
                <ElTableColumn label="Judge" width="100">
                  <template #default="scope">
                    {{ score(scope.row.faithfulness) }} /
                    {{ score(scope.row.answer_relevance) }}
                  </template>
                </ElTableColumn>
                <ElTableColumn label="错误" min-width="180">
                  <template #default="scope">
                    {{ scope.row.error ?? '-' }}
                  </template>
                </ElTableColumn>
              </ElTable>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.result-table-wrap {
  border: 1px solid #d3dfe1;
  border-radius: 8px;
  background: #ffffff;
  overflow-x: auto;
  padding: 1rem;
}

.result-table {
  width: 100%;
  min-width: 70rem;
  border-collapse: collapse;
}

.result-table th,
.result-table td {
  border-bottom: 1px solid #e0e9ea;
  padding: 0.75rem;
  text-align: left;
  vertical-align: top;
}

.result-table th {
  color: #65787d;
  font-size: 0.75rem;
  text-transform: uppercase;
}

.result-table td > span {
  display: block;
  color: #75878c;
  font-size: 0.75rem;
}

.detail-row td {
  background: #f7f9f9;
}
</style>
