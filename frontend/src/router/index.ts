// Vue 概念：Vue Router 将 URL 映射到页面组件，页面切换无需整页刷新。
// Vue 概念：createWebHistory 使用浏览器 History API，适合正常 Web 应用。
// Vue 概念：routes 中的 component 由 RouterView 动态渲染。

import { createRouter, createWebHistory } from 'vue-router'

import ChatView from '../views/ChatView.vue'
import DocumentsView from '../views/DocumentsView.vue'
import EvaluationView from '../views/EvaluationView.vue'
import LoginView from '../views/LoginView.vue'
import SearchDebugView from '../views/SearchDebugView.vue'
import { fetchAuthSession } from '../api/auth'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { public: true },
    },
    { path: '/chat', name: 'chat', component: ChatView },
    { path: '/documents', name: 'documents', component: DocumentsView },
    { path: '/search', name: 'search-debug', component: SearchDebugView },
    { path: '/evaluation', name: 'evaluation', component: EvaluationView },
  ],
})

router.beforeEach(async (to) => {
  if (to.meta.public === true) {
    return true
  }
  try {
    const session = await fetchAuthSession()
    if (session.authenticated) {
      return true
    }
  } catch {
    // 网络或服务异常统一回到登录页，由页面展示可重试状态。
  }
  return { name: 'login', query: { redirect: to.fullPath } }
})
