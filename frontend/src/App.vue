<!-- Vue 概念：RouterView 根据当前 URL 渲染聊天、文档或检索页面。 -->
<!-- Vue 概念：RouterLink 负责声明式导航，并自动提供 active 状态。 -->
<!-- Vue 概念：根组件提供全局框架，页面组件只关注各自业务。 -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  FileStack,
  FlaskConical,
  LogOut,
  MessageSquareText,
  Search,
} from 'lucide-vue-next'

import { fetchAuthSession, logout } from './api/auth'

const route = useRoute()
const router = useRouter()
const authRequired = ref(false)

interface HealthPayload {
  status: string
  model_gateway: { configured: boolean }
}

const modelStatus = ref<'checking' | 'configured' | 'missing' | 'offline'>(
  'checking',
)

async function checkModelStatus(retryCount = 0): Promise<void> {
  try {
    const response = await fetch('/api/health')
    if (!response.ok) {
      modelStatus.value = 'offline'
      return
    }
    const payload = (await response.json()) as HealthPayload
    modelStatus.value = payload.model_gateway.configured
      ? 'configured'
      : 'missing'
  } catch {
    modelStatus.value = 'offline'
    if (retryCount < 5) {
      globalThis.setTimeout(() => {
        void checkModelStatus(retryCount + 1)
      }, 1500)
    }
  }
}

onMounted(() => {
  void checkModelStatus()
  void fetchAuthSession()
    .then((session) => {
      authRequired.value = session.auth_required
    })
    .catch(() => {
      authRequired.value = false
    })
})

async function signOut(): Promise<void> {
  await logout()
  await router.replace('/login')
}
</script>

<template>
  <div class="app-layout">
    <header v-if="route.name !== 'login'" class="app-header">
      <RouterLink class="brand" to="/chat">
        <span class="brand-mark">DM</span>
        <span>DocMind</span>
      </RouterLink>
      <nav class="main-nav" aria-label="主导航">
        <span class="model-status" :data-status="modelStatus">
          模型：{{ modelStatus }}
        </span>
        <RouterLink to="/chat">
          <MessageSquareText :size="17" />
          聊天
        </RouterLink>
        <RouterLink to="/documents">
          <FileStack :size="17" />
          文档
        </RouterLink>
        <RouterLink to="/search">
          <Search :size="17" />
          检索调试
        </RouterLink>
        <RouterLink to="/evaluation">
          <FlaskConical :size="17" />
          评测
        </RouterLink>
        <button
          v-if="authRequired"
          class="logout-button"
          type="button"
          aria-label="退出登录"
          @click="signOut"
        >
          <LogOut :size="17" />
          退出
        </button>
      </nav>
    </header>
    <main class="app-content">
      <RouterView />
    </main>
  </div>
</template>
