// Vue 概念：Vite 是开发服务器和构建工具，Vue 单文件组件由插件编译。
// Vue 概念：开发时把 /api 代理到 FastAPI，可避免浏览器跨域配置。
// Vue 概念：Vitest 复用 Vite 配置，因此测试和开发环境保持一致。

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 15173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:18000',
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 15174,
    strictPort: true,
  },
  test: {
    clearMocks: true,
    environment: 'jsdom',
    include: ['src/**/*.spec.ts'],
  },
})
