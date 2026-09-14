// Vue 概念：组件测试把 App.vue 挂载到 jsdom，并模拟用户输入和提交。
// Vue 概念：Pinia 测试通过 createPinia() 创建独立状态，不会污染其他测试。
// Vue 概念：mock API 能验证组件与状态联动，而无需启动真实后端或模型。

import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

import type { ChatStreamHandlers } from './types/chat'

vi.mock('./api/chatStream', () => ({
  streamChat: vi.fn(
    async (
      _query: string,
      _signal: AbortSignal,
      handlers: ChatStreamHandlers,
    ) => {
      handlers.onRetrieval({
        type: 'retrieval',
        latency_ms: 12,
        chunk_count: 1,
      })
      handlers.onAnswer({ type: 'answer', delta: '最小 SSE ' })
      handlers.onAnswer({ type: 'answer', delta: '已经跑通。' })
      handlers.onDone({ type: 'done', citations: [1] })
    },
  ),
}))

import App from './App.vue'

describe('App', () => {
  it('submits a question and renders streamed answer deltas', async () => {
    const wrapper = mount(App, {
      global: {
        plugins: [createPinia()],
      },
    })

    await wrapper.get('textarea').setValue('DocMind 是什么？')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('.answer-text').text()).toBe('最小 SSE 已经跑通。')
    expect(wrapper.get('.retrieval-summary').text()).toContain('1 个片段')
    expect(wrapper.text()).toContain('completed')
  })
})
