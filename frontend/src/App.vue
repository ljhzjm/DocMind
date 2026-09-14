<!-- Vue 概念：<script setup> 会把 ref、computed 和 store 状态直接暴露给模板。 -->
<!-- Vue 概念：v-model 实现输入框与 Pinia 状态的双向绑定。 -->
<!-- Vue 概念：v-if / v-for 根据响应式状态决定显示内容。 -->
<script setup lang="ts">
import { useChatStore } from './stores/chat'

const chat = useChatStore()

function submit(): void {
  void chat.send()
}
</script>

<template>
  <main class="demo-shell">
    <header class="demo-header">
      <div>
        <p class="eyebrow">SSE minimal demo</p>
        <h1>DocMind</h1>
      </div>
      <span class="status-pill">{{ chat.status }}</span>
    </header>

    <form class="query-form" @submit.prevent="submit">
      <label for="query">问题</label>
      <textarea
        id="query"
        v-model="chat.query"
        rows="3"
        placeholder="例如：DocMind 支持哪些文档格式？"
        :disabled="chat.isStreaming"
        @keydown.ctrl.enter="submit"
      />
      <div class="form-actions">
        <button type="submit" :disabled="!chat.canSend">发送</button>
        <button
          type="button"
          class="secondary"
          :disabled="!chat.isStreaming"
          @click="chat.stop"
        >
          停止生成
        </button>
      </div>
    </form>

    <p v-if="chat.retrievalSummary" class="retrieval-summary">
      {{ chat.retrievalSummary }}
    </p>

    <section class="answer-panel" aria-live="polite">
      <p class="panel-label">流式回答</p>
      <p v-if="chat.answer" class="answer-text">{{ chat.answer }}</p>
      <p v-else class="placeholder">发送问题后，回答会在这里逐段出现。</p>
    </section>

    <p v-if="chat.errorMessage" class="error-message">
      {{ chat.errorMessage }}
    </p>
  </main>
</template>
