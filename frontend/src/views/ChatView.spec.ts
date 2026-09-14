// Vue 概念：组件测试把 ChatView 挂载到 jsdom，并模拟用户输入和提交。
// Vue 概念：Pinia 测试通过 createPinia() 创建独立状态，不会污染其他测试。
// Vue 概念：mock SSE API 能验证消息列表和流式状态，而无需真实后端。

import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

import type { ChatStreamHandlers } from '../types/chat'

vi.mock('../api/chatStream', () => ({
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
        trace_id: 'trace-test',
        cached: false,
        contexts: [
          {
            citation_number: 1,
            chunk_id: 'chunk-1',
            content: 'DocMind 是一个知识库问答系统。',
            document_name: 'guide.md',
            page_number: 1,
            heading_path: ['介绍'],
            score: 0.9,
          },
        ],
      })
      handlers.onAnswer({ type: 'answer', delta: 'DocMind 是' })
      handlers.onAnswer({ type: 'answer', delta: '知识库问答系统 [1]。' })
      handlers.onDone({
        type: 'done',
        citations: [1],
        trace_id: 'trace-test',
        model: 'test-model',
        usage: { input_tokens: 1, output_tokens: 1, total_tokens: 2 },
      })
    },
  ),
}))

import ChatView from './ChatView.vue'

describe('ChatView', () => {
  it('renders streamed Markdown and citation context', async () => {
    vi.useFakeTimers()
    const wrapper = mount(ChatView, {
      global: {
        plugins: [createPinia(), ElementPlus],
      },
    })

    await wrapper.get('textarea').setValue('DocMind 是什么？')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(20)
    await flushPromises()

    const partialText = wrapper.get('.markdown-body').text()
    expect(partialText.length).toBeGreaterThan(0)
    expect(partialText).not.toContain('知识库问答系统')

    await vi.runAllTimersAsync()
    await flushPromises()

    expect(wrapper.get('.markdown-body').text()).toContain('知识库问答系统')
    expect(wrapper.get('.citation-ref').text()).toBe('[1]')
    expect(wrapper.get('.retrieval-line').text()).toContain('1 个片段')
    vi.useRealTimers()
  })
})
