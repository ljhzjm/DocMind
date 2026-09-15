<!-- Vue 概念：ref 保存表单输入和错误状态，提交后由 Pinia/API 处理登录。 -->
<!-- Vue 概念：路由守卫会在进入业务页面之前检查 HttpOnly 会话 Cookie。 -->
<!-- Vue 概念：登录成功后 router.replace 会切换到用户原本要访问的页面。 -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElAlert, ElButton, ElInput } from 'element-plus'
import { KeyRound, LogIn } from 'lucide-vue-next'

import { fetchAuthSession, loginWithApiKey } from '../api/auth'

const route = useRoute()
const router = useRouter()
const apiKey = ref('')
const loading = ref(false)
const errorMessage = ref('')

onMounted(async () => {
  try {
    const session = await fetchAuthSession()
    if (session.authenticated) {
      await router.replace('/chat')
    }
  } catch {
    // 保持登录页可用，具体错误在提交时展示。
  }
})

async function submit(): Promise<void> {
  const key = apiKey.value.trim()
  if (!key || loading.value) {
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    await loginWithApiKey(key)
    const redirect =
      typeof route.query.redirect === 'string' ? route.query.redirect : '/chat'
    await router.replace(redirect.startsWith('/') ? redirect : '/chat')
  } catch (error: unknown) {
    errorMessage.value =
      error instanceof Error ? error.message : '登录失败，请重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-panel">
      <div class="login-mark"><KeyRound :size="24" /></div>
      <p class="eyebrow">DocMind Access</p>
      <h1>访问知识库</h1>
      <p class="login-help">
        输入管理员提供的访问密钥。密钥只用于建立会话，不会保存到浏览器存储。
      </p>
      <ElAlert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        :closable="false"
        show-icon
      />
      <ElInput
        v-model="apiKey"
        type="password"
        size="large"
        placeholder="访问密钥"
        show-password
        autocomplete="current-password"
        @keyup.enter="submit"
      />
      <ElButton
        type="primary"
        size="large"
        :icon="LogIn"
        :loading="loading"
        :disabled="!apiKey.trim()"
        @click="submit"
      >
        登录
      </ElButton>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  display: grid;
  min-height: 100vh;
  place-items: center;
  background:
    linear-gradient(135deg, rgb(15 118 110 / 12%), transparent 45%), #f4f8f7;
  padding: 1.5rem;
}

.login-panel {
  display: grid;
  width: min(26rem, 100%);
  gap: 1rem;
  border: 1px solid #ccdcdb;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 24px 70px rgb(22 55 58 / 14%);
  padding: 2rem;
}

.login-mark {
  display: grid;
  width: 3rem;
  height: 3rem;
  place-items: center;
  border-radius: 8px;
  background: #0f766e;
  color: #ffffff;
}

.eyebrow {
  margin: 0;
  color: #0f766e;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  color: #183438;
  font-size: 1.75rem;
}

.login-help {
  margin: 0;
  color: #5a6f74;
  line-height: 1.65;
}
</style>
