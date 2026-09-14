// Vue 概念：Vue Router 将 URL 映射到页面组件，页面切换无需整页刷新。
// Vue 概念：createWebHistory 使用浏览器 History API，适合正常 Web 应用。
// Vue 概念：routes 中的 component 由 RouterView 动态渲染。

import { createRouter, createWebHistory } from 'vue-router'

import ChatView from '../views/ChatView.vue'
import DocumentsView from '../views/DocumentsView.vue'
import EvaluationView from '../views/EvaluationView.vue'
import SearchDebugView from '../views/SearchDebugView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/chat', name: 'chat', component: ChatView },
    { path: '/documents', name: 'documents', component: DocumentsView },
    { path: '/search', name: 'search-debug', component: SearchDebugView },
    { path: '/evaluation', name: 'evaluation', component: EvaluationView },
  ],
})
