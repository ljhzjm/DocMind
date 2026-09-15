<!-- Vue 概念：props 接收数据集和检索配置，组件内部负责校准请求。 -->
<!-- Vue 概念：emit 把校准结果或错误交回评测页面统一管理。 -->
<!-- Vue 概念：ref 控制按钮 loading，避免同一配置重复提交。 -->
<script setup lang="ts">
import { ref } from 'vue'
import { ElButton } from 'element-plus'

import { calibrateRefusalThreshold } from '../api/evaluation'
import type {
  RefusalThresholdCalibration,
  RetrievalConfigInput,
} from '../types/evaluation'

const props = defineProps<{
  datasetName: string
  config: RetrievalConfigInput
  threshold?: RefusalThresholdCalibration
}>()

const emit = defineEmits<{
  calibrated: [value: RefusalThresholdCalibration]
  error: [message: string]
}>()

const loading = ref(false)

async function calibrate(): Promise<void> {
  if (!props.datasetName) {
    return
  }
  loading.value = true
  try {
    emit(
      'calibrated',
      await calibrateRefusalThreshold(props.datasetName, props.config),
    )
  } catch (error: unknown) {
    emit('error', error instanceof Error ? error.message : '拒答阈值校准失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="threshold-cell">
    <span v-if="threshold">阈值 {{ threshold.threshold.toFixed(3) }}</span>
    <span v-else>未校准</span>
    <ElButton text type="primary" :loading="loading" @click="calibrate">
      校准
    </ElButton>
  </div>
</template>

<style scoped>
.threshold-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.45rem;
  color: #52666b;
  font-size: 0.8rem;
}
</style>
