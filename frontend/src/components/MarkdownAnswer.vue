<!-- Vue 概念：computed 会根据 answer 内容自动重新计算 Markdown HTML。 -->
<!-- Vue 概念：v-html 渲染经过 DOMPurify 清洗的 Markdown，避免直接信任模型输出。 -->
<!-- Vue 概念：组件通过 defineProps 接收消息和引用片段，父组件无需操作 DOM。 -->
<script setup lang="ts">
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { computed, ref } from 'vue'

import type { CitationContext } from '../types/chat'

const props = defineProps<{
  content: string
  contexts: CitationContext[]
}>()

interface TooltipState {
  context: CitationContext
  top: number
  left: number
}

const tooltip = ref<TooltipState | null>(null)

const renderedHtml = computed(() => {
  const withCitationTags = props.content.replace(
    /\[(\d+)\]/g,
    '<sup class="citation-ref" data-citation="$1">[$1]</sup>',
  )
  return DOMPurify.sanitize(marked.parse(withCitationTags) as string)
})

function showCitation(event: MouseEvent): void {
  if (!(event.target instanceof HTMLElement)) {
    return
  }
  const element = event.target.closest<HTMLElement>('.citation-ref')
  if (element === null) {
    return
  }
  const citationNumber = Number(element.dataset.citation)
  const context = props.contexts.find(
    (item) => item.citation_number === citationNumber,
  )
  if (context === undefined) {
    return
  }
  const rect = element.getBoundingClientRect()
  tooltip.value = {
    context,
    top: rect.bottom + 8,
    left: Math.min(rect.left, window.innerWidth - 380),
  }
}
</script>

<template>
  <!-- eslint-disable vue/no-v-html -- DOMPurify sanitizes Marked output. -->
  <div
    class="markdown-body"
    @mouseover="showCitation"
    @mouseleave="tooltip = null"
    v-html="renderedHtml"
  />
  <!-- eslint-enable vue/no-v-html -->

  <Teleport to="body">
    <aside
      v-if="tooltip"
      class="citation-tooltip"
      :style="{ top: `${tooltip.top}px`, left: `${tooltip.left}px` }"
    >
      <strong>
        [{{ tooltip.context.citation_number }}]
        {{ tooltip.context.document_name }}
      </strong>
      <span v-if="tooltip.context.page_number">
        第 {{ tooltip.context.page_number }} 页
      </span>
      <p>{{ tooltip.context.content }}</p>
    </aside>
  </Teleport>
</template>

<style scoped>
.markdown-body {
  line-height: 1.75;
}

.markdown-body :deep(p) {
  margin: 0 0 0.9rem;
}

.markdown-body :deep(.citation-ref) {
  margin-left: 0.15rem;
  color: #0f766e;
  cursor: help;
  font-size: 0.75em;
  font-weight: 800;
}

.citation-tooltip {
  position: fixed;
  z-index: 3000;
  width: min(22rem, calc(100vw - 2rem));
  border: 1px solid #b7c9cc;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 18px 50px rgb(16 39 44 / 18%);
  padding: 0.85rem;
  pointer-events: none;
}

.citation-tooltip strong,
.citation-tooltip span {
  display: block;
}

.citation-tooltip span {
  margin-top: 0.2rem;
  color: #66787d;
  font-size: 0.78rem;
}

.citation-tooltip p {
  margin: 0.6rem 0 0;
  color: #26373d;
  font-size: 0.86rem;
  line-height: 1.55;
}
</style>
