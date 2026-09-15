<!-- Vue 概念：ref 保存数据集、配置行和评测结果，变更会自动更新模板。 -->
<!-- Vue 概念：v-for 渲染多个检索配置行和每个配置的指标结果。 -->
<!-- Vue 概念：async 事件处理函数在请求前后切换 loading 状态。 -->
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  ElButton,
  ElInput,
  ElInputNumber,
  ElOption,
  ElProgress,
  ElSelect,
  ElSwitch,
} from 'element-plus'
import { Ban, Play, Plus, RefreshCcw, Trash2 } from 'lucide-vue-next'

import {
  fetchEvalDatasets,
  fetchEvaluationRuns,
  fetchRefusalThresholds,
} from '../api/evaluation'
import EvaluationDatasetVersion from '../components/EvaluationDatasetVersion.vue'
import EvaluationResults from '../components/EvaluationResults.vue'
import EvaluationThresholdCell from '../components/EvaluationThresholdCell.vue'
import { useEvaluationRun } from '../composables/useEvaluationRun'
import type {
  EvalDatasetSummary,
  EvaluationRunSummary,
  RefusalThresholdCalibration,
  RetrievalConfigInput,
} from '../types/evaluation'

const datasets = ref<EvalDatasetSummary[]>([])
const datasetName = ref('')
const loading = ref(false)
const errorMessage = ref('')
const evaluationRuns = ref<EvaluationRunSummary[]>([])
const thresholds = ref<RefusalThresholdCalibration[]>([])
const selectedRunId = ref('')
const evaluationRun = useEvaluationRun()
const canResume = computed(
  () =>
    evaluationRun.status.value === 'failed' ||
    evaluationRun.status.value === 'cancelled',
)
const actionLabel = computed(() =>
  evaluationRun.isActive.value
    ? '取消评测'
    : canResume.value
      ? '继续评测'
      : '运行评测',
)
const actionType = computed<'primary' | 'danger' | 'warning'>(() =>
  evaluationRun.isActive.value
    ? 'danger'
    : canResume.value
      ? 'warning'
      : 'primary',
)
const actionIcon = computed(() =>
  evaluationRun.isActive.value ? Ban : canResume.value ? RefreshCcw : Play,
)
const configs = ref<RetrievalConfigInput[]>([
  { name: '向量 Top5', mode: 'vector', top_k: 5, rerank: false },
  { name: 'BM25 Top5', mode: 'bm25', top_k: 5, rerank: false },
  { name: '混合 + 重排', mode: 'hybrid', top_k: 5, rerank: true },
])

onMounted(async () => {
  try {
    datasets.value = await fetchEvalDatasets()
    evaluationRuns.value = await fetchEvaluationRuns()
    thresholds.value = await fetchRefusalThresholds()
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

function thresholdFor(
  config: RetrievalConfigInput,
): RefusalThresholdCalibration | undefined {
  return thresholds.value.find(
    (item) =>
      item.mode === config.mode &&
      item.top_k === config.top_k &&
      (config.rerank
        ? item.rerank_provider !== 'none'
        : item.rerank_provider === 'none'),
  )
}

function updateThreshold(calibrated: RefusalThresholdCalibration): void {
  thresholds.value = [
    ...thresholds.value.filter(
      (item) =>
        !(
          item.mode === calibrated.mode &&
          item.top_k === calibrated.top_k &&
          item.rerank_provider === calibrated.rerank_provider
        ),
    ),
    calibrated,
  ]
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

async function primaryAction(): Promise<void> {
  loading.value = true
  try {
    if (evaluationRun.isActive.value) {
      await evaluationRun.cancel()
    } else if (canResume.value) {
      await evaluationRun.resume()
      evaluationRuns.value = await fetchEvaluationRuns()
    } else {
      await run()
    }
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
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
        :type="actionType"
        :icon="actionIcon"
        :loading="loading"
        :disabled="loading"
        @click="primaryAction"
      >
        {{ actionLabel }}
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
        <EvaluationDatasetVersion
          :dataset-name="datasetName"
          @error="errorMessage = $event"
        />
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
            :label="`${runItem.dataset_name} · v${runItem.dataset_revision ?? '-'} · ${runItem.status} · ${new Date(runItem.created_at).toLocaleString()}`"
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
        <EvaluationThresholdCell
          :dataset-name="datasetName"
          :config="config"
          :threshold="thresholdFor(config)"
          @calibrated="updateThreshold"
          @error="errorMessage = $event"
        />
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

<style scoped src="./evaluation-view.css"></style>
