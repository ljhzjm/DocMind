<!-- Vue 概念：v-for 渲染多会话和消息列表，:key 帮助 Vue 高效更新节点。 -->
<!-- Vue 概念：watch/nextTick 用于回答变化后自动滚动到最新内容。 -->
<!-- Vue 概念：Pinia action 负责 send、stop 和切换会话，组件只触发事件。 -->
<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { ElButton, ElDrawer, ElEmpty, ElInput, ElTag } from 'element-plus'
import { Plus, Send, Square, Trash2 } from 'lucide-vue-next'

import MarkdownAnswer from '../components/MarkdownAnswer.vue'
import type { CitationContext } from '../types/chat'
import { useChatStore } from '../stores/chat'

const chat = useChatStore()
const scrollContainer = ref<HTMLElement | null>(null)
const selectedCitation = ref<CitationContext | null>(null)

onMounted(() => {
  void chat.loadSessions()
})

watch(
  () => {
    const session = chat.activeSession
    const messages = session?.messages ?? []
    const last = messages[messages.length - 1]
    return `${last?.content ?? ''}:${last?.streaming ?? false}`
  },
  async () => {
    await nextTick()
    const container = scrollContainer.value
    if (container === null) {
      return
    }
    if (typeof container.scrollTo === 'function') {
      container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' })
    } else {
      container.scrollTop = container.scrollHeight
    }
  },
)
</script>

<template>
  <section class="chat-page">
    <aside class="session-sidebar">
      <div class="session-header">
        <strong>会话</strong>
        <ElButton
          :icon="Plus"
          circle
          aria-label="新建会话"
          @click="chat.newSession"
        />
      </div>
      <button
        v-for="session in chat.sessions"
        :key="session.id"
        class="session-item"
        :class="{ active: session.id === chat.activeSessionId }"
        type="button"
        @click="chat.selectSession(session.id)"
      >
        <span>{{ session.title }}</span>
        <Trash2
          :size="15"
          aria-label="删除会话"
          @click.stop="chat.deleteSession(session.id)"
        />
      </button>
    </aside>

    <section class="conversation">
      <div ref="scrollContainer" class="message-list">
        <ElEmpty
          v-if="!chat.activeSession?.messages.length"
          description="输入问题开始对话"
        />
        <article
          v-for="message in chat.activeSession?.messages"
          :key="message.id"
          class="message-row"
          :class="message.role"
        >
          <div class="message-bubble">
            <MarkdownAnswer
              v-if="message.role === 'assistant'"
              :content="message.content"
              :contexts="message.contexts"
              @select-context="selectedCitation = $event"
            />
            <span v-else>{{ message.content }}</span>
            <p v-if="message.error" class="message-error">
              {{ message.error }}
            </p>
            <div class="message-tags">
              <ElTag v-if="message.cached" size="small" type="warning"
                >缓存命中</ElTag
              >
              <ElTag
                v-if="message.role === 'assistant' && message.citations.length"
                size="small"
                type="success"
              >
                引用：{{ message.citations.join(', ') }}
              </ElTag>
              <code v-if="message.traceId"
                >trace: {{ message.traceId.slice(0, 12) }}</code
              >
            </div>
          </div>
        </article>
      </div>

      <p v-if="chat.retrievalSummary" class="retrieval-line">
        {{ chat.retrievalSummary }}
      </p>

      <form class="composer" @submit.prevent="chat.send">
        <ElInput
          v-model="chat.query"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="输入问题，Ctrl + Enter 发送"
          :disabled="chat.isStreaming"
          @keydown.ctrl.enter.prevent="chat.send"
        />
        <ElButton
          v-if="!chat.isStreaming"
          type="primary"
          :icon="Send"
          :disabled="!chat.canSend"
          native-type="submit"
        >
          发送
        </ElButton>
        <ElButton v-else :icon="Square" @click="chat.stop">停止生成</ElButton>
      </form>
    </section>

    <ElDrawer
      :model-value="selectedCitation !== null"
      title="引用片段"
      size="min(40rem, 92vw)"
      @close="selectedCitation = null"
    >
      <template v-if="selectedCitation">
        <h3>{{ selectedCitation.document_name }}</h3>
        <p>
          {{
            selectedCitation.page_number
              ? `第 ${selectedCitation.page_number} 页`
              : '未知页码'
          }}
          · {{ selectedCitation.heading_path.join(' > ') || '无标题路径' }}
        </p>
        <p class="citation-content">{{ selectedCitation.content }}</p>
      </template>
    </ElDrawer>
  </section>
</template>

<style scoped>
.chat-page {
  display: grid;
  grid-template-columns: 16rem minmax(0, 1fr);
  min-height: calc(100vh - 5rem);
  gap: 1rem;
}

.session-sidebar,
.conversation {
  border: 1px solid #d6e0e2;
  border-radius: 8px;
  background: #ffffff;
}

.session-sidebar {
  padding: 0.75rem;
}

.session-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.session-item {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #33474d;
  cursor: pointer;
  padding: 0.75rem;
  text-align: left;
}

.session-item.active {
  background: #e8f3f1;
  color: #0f665f;
}

.conversation {
  display: grid;
  min-height: 0;
  grid-template-rows: minmax(0, 1fr) auto auto;
  overflow: hidden;
}

.message-list {
  min-height: 24rem;
  overflow-y: auto;
  padding: 1.25rem;
}

.message-row {
  display: flex;
  margin-bottom: 1rem;
}

.message-row.user {
  justify-content: flex-end;
}

.message-bubble {
  max-width: min(48rem, 88%);
  border-radius: 8px;
  background: #f2f6f7;
  padding: 0.9rem 1rem;
}

.message-row.user .message-bubble {
  background: #e2efed;
}

.citation-content {
  white-space: pre-wrap;
  line-height: 1.75;
}

.message-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.55rem;
}

code {
  color: #6b7f84;
  font-size: 0.72rem;
}

.message-error {
  margin: 0.5rem 0 0;
  color: #a3302b;
  font-size: 0.85rem;
}

.retrieval-line {
  margin: 0;
  border-top: 1px solid #e1e9ea;
  color: #687a7f;
  font-size: 0.78rem;
  padding: 0.45rem 1rem;
}

.composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 0.75rem;
  border-top: 1px solid #e1e9ea;
  padding: 0.85rem;
}

@media (max-width: 760px) {
  .chat-page {
    grid-template-columns: 1fr;
  }

  .session-sidebar {
    max-height: 12rem;
    overflow-y: auto;
  }
}
</style>
