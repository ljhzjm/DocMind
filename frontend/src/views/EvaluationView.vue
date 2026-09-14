<!-- Vue 概念：ref 保存数据集、配置行和评测结果，变更会自动更新模板。 -->
<!-- Vue 概念：v-for 渲染多个检索配置行和每个配置的指标结果。 -->
<!-- Vue 概念：async 事件处理函数在请求前后切换 loading 状态。 -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  ElButton,
  ElInput,
  ElInputNumber,
  ElOption,
  ElSelect,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import { Play, Plus, Trash2 } from 'lucide-vue-next'

import {
  fetchEvalDatasets,
  fetchEvaluationRun,
  fetchEvaluationRuns,
  runEvaluation,
} from '../api/evaluation'
import type {
  ConfigMetrics,
  EvalDatasetSummary,
  EvaluationRunSummary,
  RetrievalConfigInput,
  SearchMode,
} from '../types/evaluation'

const datasets = ref<EvalDatasetSummary[]>([])
const datasetName = ref('')
const loading = ref(false)
const errorMessage = ref('')
const results = ref<ConfigMetrics[]>([])
const evaluationRuns = ref<EvaluationRunSummary[]>([])
const selectedRunId = ref('')
const configs = ref<RetrievalConfigInput[]>([
  { name: '向量 Top5', mode: 'vector', top_k: 5, rerank: false },
  { name: 'BM25 Top5', mode: 'bm25', top_k: 5, rerank: false },
  { name: '混合 + 重排', mode: 'hybrid', top_k: 5, rerank: true },
])

onMounted(async () => {
  try {
    datasets.value = await fetchEvalDatasets()
    evaluationRuns.value = await fetchEvaluationRuns()
    datasetName.value = datasets.value[0]?.dataset_name ?? ''
  } catch (error: unknown) {
    errorMessage.value =
      error instanceof Error ? error.message : '数据集加载失败'
  }
})

async function loadEvaluationRun(): Promise<void> {
  if (selectedRunId.value.length === 0) {
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await fetchEvaluationRun(selectedRunId.value)
    results.value = response.results
  } catch (error: unknown) {
    errorMessage.value =
      error instanceof Error ? error.message : '历史评测加载失败'
  } finally {
    loading.value = false
  }
}

function addConfig(): void {
  configs.value.push({
    name: `配置 ${configs.value.length + 1}`,
    mode: 'hybrid',
    top_k: 5,
    rerank: false,
  })
}

function removeConfig(index: number): void {
  configs.value.splice(index, 1)
}

async function run(): Promise<void> {
  if (datasetName.value.length === 0 || configs.value.length === 0) {
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await runEvaluation({
      dataset_name: datasetName.value,
      configs: configs.value,
    })
    results.value = response.results
    evaluationRuns.value = await fetchEvaluationRuns()
    selectedRunId.value = response.run_id
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : '评测失败'
  } finally {
    loading.value = false
  }
}

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
  <section class="evaluation-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Offline evaluation</p>
        <h2>评测中心</h2>
      </div>
      <ElButton type="primary" :icon="Play" :loading="loading" @click="run">
        运行评测
      </ElButton>
    </header>

    <section class="config-panel">
      <div class="dataset-row">
        <label>数据集</label>
        <ElSelect
          v-model="datasetName"
          placeholder="选择数据集"
          style="width: 18rem"
        >
          <ElOption
            v-for="dataset in datasets"
            :key="dataset.dataset_name"
            :label="`${dataset.dataset_name} (${dataset.case_count})`"
            :value="dataset.dataset_name"
          />
        </ElSelect>
        <ElButton :icon="Plus" @click="addConfig">添加配置</ElButton>
      </div>

      <div class="history-row">
        <label>历史运行</label>
        <ElSelect
          v-model="selectedRunId"
          placeholder="选择历史评测"
          style="width: 24rem"
        >
          <ElOption
            v-for="evaluationRun in evaluationRuns"
            :key="evaluationRun.run_id"
            :label="`${evaluationRun.dataset_name} · ${new Date(evaluationRun.created_at).toLocaleString()}`"
            :value="evaluationRun.run_id"
          />
        </ElSelect>
        <ElButton :disabled="!selectedRunId" @click="loadEvaluationRun">
          加载历史
        </ElButton>
      </div>

      <div v-for="(config, index) in configs" :key="index" class="config-row">
        <ElInput v-model="config.name" placeholder="配置名称" />
        <ElSelect v-model="config.mode">
          <ElOption label="Vector" value="vector" />
          <ElOption label="BM25" value="bm25" />
          <ElOption label="Hybrid" value="hybrid" />
        </ElSelect>
        <ElInputNumber v-model="config.top_k" :min="1" :max="50" />
        <label class="switch-label">
          重排
          <ElSwitch v-model="config.rerank" />
        </label>
        <ElButton
          :icon="Trash2"
          circle
          :disabled="configs.length === 1"
          @click="removeConfig(index)"
        />
      </div>
    </section>

    <p v-if="errorMessage" class="page-error">{{ errorMessage }}</p>

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
                <span
                  >{{ modeLabel(result.mode) }} · top{{ result.top_k }}</span
                >
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
                    <template #default="scope">{{
                      percent(scope.row.recall_at_5)
                    }}</template>
                  </ElTableColumn>
                  <ElTableColumn label="RR" width="80">
                    <template #default="scope">{{
                      score(scope.row.reciprocal_rank)
                    }}</template>
                  </ElTableColumn>
                  <ElTableColumn label="Judge" width="100">
                    <template #default="scope">
                      {{ score(scope.row.faithfulness) }} /
                      {{ score(scope.row.answer_relevance) }}
                    </template>
                  </ElTableColumn>
                  <ElTableColumn label="错误" min-width="180">
                    <template #default="scope">{{
                      scope.row.error ?? '-'
                    }}</template>
                  </ElTableColumn>
                </ElTable>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.evaluation-page {
  display: grid;
  gap: 1rem;
}

.page-header,
.dataset-row,
.history-row,
.config-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.page-header {
  justify-content: space-between;
}

.page-header h2 {
  margin: 0;
}

.eyebrow {
  margin: 0 0 0.3rem;
  color: #0f766e;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.config-panel,
.result-table-wrap {
  border: 1px solid #d3dfe1;
  border-radius: 8px;
  background: #ffffff;
  padding: 1rem;
}

.config-panel {
  display: grid;
  gap: 0.75rem;
}

.dataset-row {
  flex-wrap: wrap;
}

.history-row {
  border-top: 1px solid #e2eaeb;
  padding-top: 0.75rem;
}

.config-row {
  display: grid;
  grid-template-columns: minmax(10rem, 1.4fr) 9rem 7rem 7rem auto;
  border-top: 1px solid #e2eaeb;
  padding-top: 0.75rem;
}

.switch-label {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  color: #52666b;
}

.result-table {
  width: 100%;
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

.page-error {
  color: #a3302b;
}

@media (max-width: 900px) {
  .config-row {
    grid-template-columns: 1fr;
  }

  .result-table-wrap {
    overflow-x: auto;
  }

  .result-table {
    min-width: 70rem;
  }
}
</style>
