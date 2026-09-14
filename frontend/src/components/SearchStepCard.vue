<!-- Vue 概念：defineProps 声明组件输入，父组件通过属性传递步骤数据。 -->
<!-- Vue 概念：computed 格式化展示值，模板中保持简单。 -->
<!-- Vue 概念：v-for 渲染该步骤返回的候选片段列表。 -->
<script setup lang="ts">
import { computed } from 'vue'

import type { SearchStep } from '../types/search'

const props = defineProps<{
  title: string
  step: SearchStep
  accent: 'rewrite' | 'vector' | 'bm25' | 'fusion' | 'rerank'
}>()

const status = computed(() =>
  props.step.error === null
    ? `${props.step.latency_ms.toFixed(1)} ms`
    : 'error',
)
</script>

<template>
  <article class="debug-step" :data-accent="accent">
    <header>
      <div>
        <span class="step-dot" />
        <strong>{{ title }}</strong>
      </div>
      <div class="step-meta">
        <span>{{ step.results.length }} results</span>
        <code>{{ status }}</code>
      </div>
    </header>

    <p v-if="step.error" class="step-error">{{ step.error }}</p>
    <div v-else-if="step.results.length === 0" class="step-empty">无结果</div>
    <ol v-else class="result-list">
      <li v-for="result in step.results.slice(0, 5)" :key="result.chunk_id">
        <div class="result-heading">
          <span>{{ result.document_name }}</span>
          <code>{{ result.score.toFixed(4) }}</code>
        </div>
        <p class="result-path">
          {{ result.page_number ? `p.${result.page_number}` : 'no page' }}
          <span v-if="result.heading_path.length">
            · {{ result.heading_path.join(' > ') }}
          </span>
        </p>
        <p class="result-content">{{ result.content }}</p>
        <div class="source-tags">
          <span v-for="source in result.sources" :key="source">{{
            source
          }}</span>
        </div>
      </li>
    </ol>
  </article>
</template>

<style scoped>
.debug-step {
  --accent: #7dd3c7;
  border: 1px solid #33454b;
  border-left: 3px solid var(--accent);
  border-radius: 8px;
  background: #172126;
  padding: 0.9rem;
}

.debug-step[data-accent='vector'] {
  --accent: #55b8d9;
}

.debug-step[data-accent='bm25'] {
  --accent: #e2a84f;
}

.debug-step[data-accent='fusion'] {
  --accent: #d58ac8;
}

.debug-step[data-accent='rerank'] {
  --accent: #9bc76a;
}

header,
.result-heading,
.step-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

header > div {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.step-dot {
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 50%;
  background: var(--accent);
}

.step-meta,
.result-path {
  color: #8fa4aa;
  font-size: 0.75rem;
}

code {
  color: var(--accent);
}

.step-error {
  color: #f29c94;
}

.step-empty {
  color: #74888e;
  font-size: 0.85rem;
}

.result-list {
  display: grid;
  gap: 0.65rem;
  margin: 0.85rem 0 0;
  padding: 0;
  list-style: none;
}

.result-list li {
  border-top: 1px solid #2e4045;
  padding-top: 0.65rem;
}

.result-path,
.result-content {
  margin: 0.3rem 0 0;
}

.result-content {
  display: -webkit-box;
  overflow: hidden;
  color: #d6e0e2;
  font-size: 0.82rem;
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.source-tags {
  display: flex;
  gap: 0.3rem;
  margin-top: 0.45rem;
}

.source-tags span {
  border: 1px solid #43575d;
  border-radius: 999px;
  color: #b8c8cc;
  font-size: 0.68rem;
  padding: 0.1rem 0.4rem;
}
</style>
