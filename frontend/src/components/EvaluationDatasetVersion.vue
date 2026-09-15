<!-- Vue 概念：props 接收当前数据集名称，watch 在切换数据集时刷新版本。 -->
<!-- Vue 概念：组件独立管理版本加载和冻结状态，避免页面组件继续膨胀。 -->
<!-- Vue 概念：emit 把错误交给父页面统一显示。 -->
<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElButton } from 'element-plus'

import {
  fetchEvalDatasetVersions,
  freezeEvalDatasetVersion,
} from '../api/evaluation'

const props = defineProps<{
  datasetName: string
}>()

const emit = defineEmits<{
  error: [message: string]
}>()

const latestRevision = ref(0)
const loading = ref(false)

watch(
  () => props.datasetName,
  () => {
    void loadVersions()
  },
  { immediate: true },
)

async function loadVersions(): Promise<void> {
  if (!props.datasetName) {
    latestRevision.value = 0
    return
  }
  try {
    const versions = await fetchEvalDatasetVersions(props.datasetName)
    latestRevision.value = versions[0]?.revision ?? 0
  } catch (error: unknown) {
    emit('error', error instanceof Error ? error.message : '数据集版本加载失败')
  }
}

async function freezeVersion(): Promise<void> {
  if (!props.datasetName) {
    return
  }
  loading.value = true
  try {
    const version = await freezeEvalDatasetVersion(props.datasetName)
    latestRevision.value = version.revision
  } catch (error: unknown) {
    emit('error', error instanceof Error ? error.message : '数据集冻结失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <span class="revision-label">
    {{ latestRevision ? `v${latestRevision}` : '尚未冻结' }}
  </span>
  <ElButton :loading="loading" :disabled="!datasetName" @click="freezeVersion">
    冻结版本
  </ElButton>
</template>

<style scoped>
.revision-label {
  border: 1px solid #b8cfcb;
  border-radius: 999px;
  color: #0f665f;
  font-size: 0.78rem;
  font-weight: 700;
  padding: 0.35rem 0.65rem;
}
</style>
