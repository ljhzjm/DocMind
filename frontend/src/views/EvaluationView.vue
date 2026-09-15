<!-- Vue 概念：ref 保存数据集、配置行和评测结果，变更会自动更新模板。 -->
<!-- Vue 概念：v-for 渲染多个检索配置行和每个配置的指标结果。 -->
<!-- Vue 概念：async 事件处理函数在请求前后切换 loading 状态。 -->
<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import {
  ElButton,
  ElInput,
  ElInputNumber,
  ElOption,
  ElProgress,
  ElSelect,
  ElSwitch,
} from 'element-plus'
import { Play, Plus, Trash2 } from 'lucide-vue-next'

import { fetchEvalDatasets, fetchEvaluationRuns } from '../api/evaluation'
import EvaluationResults from '../components/EvaluationResults.vue'
import { useEvaluationRun } from '../composables/useEvaluationRun'
import type {
  EvalDatasetSummary,
  EvaluationRunSummary,
  RetrievalConfigInput,
} from '../types/evaluation'

const datasets = ref<EvalDatasetSummary[]>([])
const datasetName = ref('')
const loading = ref(false)
const errorMessage = ref('')
const evaluationRuns = ref<EvaluationRunSummary[]>([])
const selectedRunId = ref('')
const evaluationRun = useEvaluationRun()
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

watch(evaluationRun.status, async (status) => {
  if (status === 'completed' || status === 'failed') {
    try {
      evaluationRuns.value = await fetchEvaluationRuns()
    } catch (error: unknown) {
      errorMessage.value =
        error instanceof Error ? error.message : '评测历史刷新失败'
    }
  }
})

async function loadEvaluationRun(): Promise<void> {
  if (selectedRunId.value.length === 0) {
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    await evaluationRun.load(selectedRunId.value)
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
    const runId = await evaluationRun.start({
      dataset_name: datasetName.value,
      configs: configs.value,
    })
    evaluationRuns.value = await fetchEvaluationRuns()
    selectedRunId.value = runId
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : '评测失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="evaluation-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Offline evaluation</p>
        <h2>评测中心</h2>
      </div>
      <ElButton
        type="primary"
        :icon="Play"
        :loading="loading || evaluationRun.isActive.value"
        :disabled="evaluationRun.isActive.value"
        @click="run"
      >
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
            v-for="runItem in evaluationRuns"
            :key="runItem.run_id"
            :label="`${runItem.dataset_name} · ${runItem.status} · ${new Date(runItem.created_at).toLocaleString()}`"
            :value="runItem.run_id"
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

    <section v-if="evaluationRun.status.value !== 'idle'" class="run-progress">
      <div>
        <strong>评测状态：{{ evaluationRun.status.value }}</strong>
        <span>
          {{ evaluationRun.run.value?.progress_completed ?? 0 }} /
          {{ evaluationRun.run.value?.progress_total ?? 0 }}
        </span>
      </div>
      <ElProgress
        :percentage="evaluationRun.progress.value"
        :status="
          evaluationRun.status.value === 'failed'
            ? 'exception'
            : evaluationRun.status.value === 'completed'
              ? 'success'
              : undefined
        "
      />
    </section>

    <p v-if="errorMessage" class="page-error">{{ errorMessage }}</p>
    <p v-if="evaluationRun.errorMessage.value" class="page-error">
      {{ evaluationRun.errorMessage.value }}
    </p>
    <EvaluationResults :results="evaluationRun.results.value" />
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
.run-progress {
  border: 1px solid #d3dfe1;
  border-radius: 8px;
  background: #ffffff;
  padding: 1rem;
}

.run-progress {
  display: grid;
  gap: 0.75rem;
}

.run-progress > div {
  display: flex;
  justify-content: space-between;
  color: #52666b;
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

.page-error {
  color: #a3302b;
}

@media (max-width: 900px) {
  .config-row {
    grid-template-columns: 1fr;
  }
}
</style>
