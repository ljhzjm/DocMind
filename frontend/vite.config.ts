import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 15173,
    strictPort: true,
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
