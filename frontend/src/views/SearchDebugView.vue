<!-- Vue 概念：ref 保存调试结果、加载状态和错误信息。 -->
<!-- Vue 概念：async 事件处理函数在拿到响应后更新响应式数据。 -->
<!-- Vue 概念：子组件 SearchStepCard 通过 props 接收每个步骤的结果。 -->
<script setup lang="ts">
import { ref } from 'vue'
import {
  ElAlert,
  ElButton,
  ElInput,
  ElInputNumber,
  ElSkeleton,
} from 'element-plus'
import { Play, Search } from 'lucide-vue-next'

import SearchStepCard from '../components/SearchStepCard.vue'
import { fetchSearchDebug, fetchTraceReplay } from '../api/search'
import type { SearchDebugTrace, TraceReplay } from '../types/search'

const query = ref('企业知识库如何保证回答可追溯？')
const topK = ref(10)
const loading = ref(false)
const errorMessage = ref('')
const trace = ref<SearchDebugTrace | null>(null)
const traceId = ref('')
const replay = ref<TraceReplay | null>(null)
const replayLoading = ref(false)
const replayError = ref('')

async function replayTrace(): Promise<void> {
  const currentTraceId = traceId.value.trim()
  if (currentTraceId.length === 0) {
    return
  }
  replayLoading.value = true
  replayError.value = ''
  try {
    replay.value = await fetchTraceReplay(currentTraceId)
  } catch (error: unknown) {
    replayError.value =
      error instanceof Error ? error.message : 'Trace 回放失败'
  } finally {
    replayLoading.value = false
  }
}

async function runSearch(): Promise<void> {
  const currentQuery = query.value.trim()
  if (currentQuery.length === 0) {
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    trace.value = await fetchSearchDebug(currentQuery, topK.value)
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : '检索失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="search-debug-page">
    <header class="debug-header">
      <div>
        <p class="eyebrow">Retrieval devtools</p>
        <h2>检索调试</h2>
      </div>
      <span class="pipeline-label">rewrite → vector + bm25 → rrf → rerank</span>
    </header>

    <form class="debug-toolbar" @submit.prevent="runSearch">
      <ElInput
        v-model="query"
        :prefix-icon="Search"
        placeholder="输入检索查询"
      />
      <ElInputNumber
        v-model="topK"
        :min="1"
        :max="50"
        controls-position="right"
      />
      <ElButton
        type="primary"
        :icon="Play"
        :loading="loading"
        native-type="submit"
      >
        运行
      </ElButton>
    </form>

    <form class="trace-toolbar" @submit.prevent="replayTrace">
      <ElInput
        v-model="traceId"
        placeholder="输入 trace_id 回放"
        :prefix-icon="Search"
      />
      <ElButton :loading="replayLoading" native-type="submit"
        >回放 Trace</ElButton
      >
    </form>

    <ElAlert
      v-if="replayError"
      :title="replayError"
      type="error"
      :closable="false"
      show-icon
    />

    <section v-if="replay" class="trace-panel">
      <header>
        <strong>Trace {{ replay.trace_id }}</strong>
        <span>{{ replay.usage_records.length }} 个环节</span>
      </header>
      <table>
        <thead>
          <tr>
            <th>step</th>
            <th>model</th>
            <th>tokens</th>
            <th>latency</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="record in replay.usage_records"
            :key="`${record.step}-${record.created_at}`"
          >
            <td>{{ record.step }}</td>
            <td>{{ record.model }}</td>
            <td>{{ record.input_tokens }} / {{ record.output_tokens }}</td>
            <td>{{ record.latency_ms }} ms</td>
          </tr>
        </tbody>
      </table>
      <pre v-if="replay.snapshot">{{
        JSON.stringify(replay.snapshot, null, 2)
      }}</pre>
    </section>

    <ElAlert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      :closable="false"
      show-icon
    />

    <ElSkeleton v-if="loading" :rows="10" animated />

    <div v-else-if="trace" class="debug-grid">
      <article class="rewrite-card">
        <header>
          <div>
            <span class="stage-index">01</span><strong>查询改写</strong>
          </div>
          <code>{{ trace.rewrite.latency_ms.toFixed(1) }} ms</code>
        </header>
        <dl>
          <dt>rewritten_query</dt>
          <dd>{{ trace.rewrite.query }}</dd>
          <dt>keywords</dt>
          <dd>{{ trace.rewrite.keywords.join(', ') || '无' }}</dd>
          <dt>retrieval_query</dt>
          <dd>{{ trace.rewrite.retrieval_query }}</dd>
        </dl>
      </article>

      <SearchStepCard
        title="向量检索 · pgvector"
        :step="trace.vector"
        accent="vector"
      />
      <SearchStepCard
        title="关键词检索 · BM25"
        :step="trace.bm25"
        accent="bm25"
      />
      <SearchStepCard
        title="融合 · RRF k=60"
        :step="trace.fusion"
        accent="fusion"
      />
      <SearchStepCard
        title="重排 · reranker"
        :step="trace.rerank"
        accent="rerank"
      />
    </div>
  </section>
</template>

<style scoped>
.search-debug-page {
  display: grid;
  gap: 1rem;
}

.debug-header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 1rem;
}

.debug-header h2 {
  margin: 0;
}

.eyebrow,
.pipeline-label {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.eyebrow {
  margin: 0 0 0.3rem;
  color: #0f766e;
  font-weight: 800;
}

.pipeline-label {
  color: #61757a;
}

.debug-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 8rem auto;
  gap: 0.75rem;
  border: 1px solid #ccd9db;
  border-radius: 8px;
  background: #ffffff;
  padding: 0.85rem;
}

.debug-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.85rem;
}

.rewrite-card {
  grid-column: 1 / -1;
  border: 1px solid #33454b;
  border-left: 3px solid #7dd3c7;
  border-radius: 8px;
  background: #172126;
  color: #d6e0e2;
  padding: 0.9rem;
}

.rewrite-card header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.rewrite-card header div {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.stage-index,
.rewrite-card code {
  color: #7dd3c7;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.rewrite-card dl {
  display: grid;
  grid-template-columns: 9rem minmax(0, 1fr);
  gap: 0.35rem 0.75rem;
  margin: 0.9rem 0 0;
}

.rewrite-card dt {
  color: #8fa4aa;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 0.72rem;
}

.rewrite-card dd {
  overflow-wrap: anywhere;
  margin: 0;
}

.trace-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.75rem;
}

.trace-panel {
  border: 1px solid #33454b;
  border-radius: 8px;
  background: #172126;
  color: #d6e0e2;
  padding: 0.9rem;
}

.trace-panel header {
  display: flex;
  justify-content: space-between;
}

.trace-panel table {
  width: 100%;
  margin-top: 0.75rem;
  border-collapse: collapse;
}

.trace-panel th,
.trace-panel td {
  border-top: 1px solid #33454b;
  padding: 0.45rem;
  text-align: left;
}

.trace-panel pre {
  max-height: 18rem;
  overflow: auto;
  color: #9ccbc3;
}
@media (max-width: 800px) {
  .debug-header {
    align-items: start;
    flex-direction: column;
  }

  .debug-toolbar,
  .debug-grid {
    grid-template-columns: 1fr;
  }

  .rewrite-card dl {
    grid-template-columns: 1fr;
  }
}
</style>
