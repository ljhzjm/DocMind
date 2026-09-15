// Vue 概念：composable 把评测轮询逻辑从页面组件中抽离，便于复用和测试。
// Vue 概念：ref 保存当前 run 与错误，computed 派生结果和进度。
// Vue 概念：onUnmounted 清理定时器，避免页面离开后继续请求。

import { computed, onUnmounted, ref } from 'vue'

import { fetchEvaluationRun, runEvaluation } from '../api/evaluation'
import type {
  EvalRunRequest,
  EvalRunResponse,
  EvaluationRunStatus,
} from '../types/evaluation'

const ACTIVE_STATUSES = new Set<EvaluationRunStatus>(['queued', 'running'])
const POLL_INTERVAL_MS = 2000

export function useEvaluationRun() {
  const run = ref<EvalRunResponse | null>(null)
  const errorMessage = ref('')
  const activeRunId = ref('')
  let pollTimer: ReturnType<typeof setTimeout> | null = null

  const status = computed<EvaluationRunStatus | 'idle'>(
    () => run.value?.status ?? 'idle',
  )
  const isActive = computed(
    () => run.value !== null && ACTIVE_STATUSES.has(run.value.status),
  )
  const progress = computed(() => {
    if (run.value === null || run.value.progress_total === 0) {
      return 0
    }
    return Math.round(
      (run.value.progress_completed / run.value.progress_total) * 100,
    )
  })
  const results = computed(() => run.value?.results ?? [])

  function stopPolling(): void {
    if (pollTimer !== null) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  async function refresh(runId: string): Promise<void> {
    const response = await fetchEvaluationRun(runId)
    if (runId !== activeRunId.value) {
      return
    }
    run.value = response
    if (response.status === 'failed') {
      errorMessage.value = response.error_message ?? '评测执行失败'
    }
    if (ACTIVE_STATUSES.has(response.status)) {
      pollTimer = setTimeout(() => {
        void refresh(runId).catch((error: unknown) => {
          errorMessage.value =
            error instanceof Error ? error.message : '评测状态刷新失败'
          stopPolling()
        })
      }, POLL_INTERVAL_MS)
    } else {
      stopPolling()
    }
  }

  async function start(request: EvalRunRequest): Promise<string> {
    errorMessage.value = ''
    stopPolling()
    const accepted = await runEvaluation(request)
    activeRunId.value = accepted.run_id
    await refresh(accepted.run_id)
    return accepted.run_id
  }

  async function load(runId: string): Promise<void> {
    errorMessage.value = ''
    stopPolling()
    activeRunId.value = runId
    await refresh(runId)
  }

  onUnmounted(stopPolling)

  return {
    run,
    status,
    isActive,
    progress,
    results,
    errorMessage,
    start,
    load,
    stopPolling,
  }
}
