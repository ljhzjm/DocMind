<!-- Vue 概念：RouterView 根据当前 URL 渲染聊天、文档或检索页面。 -->
<!-- Vue 概念：RouterLink 负责声明式导航，并自动提供 active 状态。 -->
<!-- Vue 概念：根组件提供全局框架，页面组件只关注各自业务。 -->
<script setup lang="ts">
import { FileStack, MessageSquareText, Search } from 'lucide-vue-next'
</script>

<template>
  <div class="app-layout">
    <header class="app-header">
      <RouterLink class="brand" to="/chat">
        <span class="brand-mark">DM</span>
        <span>DocMind</span>
      </RouterLink>
      <nav class="main-nav" aria-label="主导航">
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
      </nav>
    </header>
    <main class="app-content">
      <RouterView />
    </main>
  </div>
</template>
