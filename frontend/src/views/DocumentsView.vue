<!-- Vue 概念：onMounted 加载文档，onUnmounted 清理轮询定时器。 -->
<!-- Vue 概念：v-if 根据上传和加载状态切换进度条、表格与空状态。 -->
<!-- Vue 概念：事件处理函数从 input 读取 File，再交给 Pinia action。 -->
<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import {
  ElButton,
  ElDrawer,
  ElProgress,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import {
  ListTree,
  RefreshCw,
  RefreshCcw,
  RotateCcw,
  Upload,
} from 'lucide-vue-next'

import { useDocumentsStore } from '../stores/documents'
import type { DocumentItem, DocumentStatus } from '../types/documents'

const documents = useDocumentsStore()
const fileInput = ref<HTMLInputElement | null>(null)

const statusLabels: Record<DocumentStatus, string> = {
  uploaded: '已上传',
  parsing: '解析中',
  ready: '已完成',
  failed: '失败',
}

const statusTypes: Record<
  DocumentStatus,
  'info' | 'warning' | 'success' | 'danger'
> = {
  uploaded: 'info',
  parsing: 'warning',
  ready: 'success',
  failed: 'danger',
}

onMounted(() => {
  void documents.loadDocuments()
})
onUnmounted(() => documents.stopPolling())

function chooseFile(): void {
  fileInput.value?.click()
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file !== undefined) {
    void documents.upload(file)
  }
  input.value = ''
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString()
}

function asDocument(row: unknown): DocumentItem {
  return row as DocumentItem
}

function statusLabel(row: unknown): string {
  return statusLabels[asDocument(row).status]
}

function statusType(row: unknown): 'info' | 'warning' | 'success' | 'danger' {
  return statusTypes[asDocument(row).status]
}

function documentSize(row: unknown): string {
  return formatSize(asDocument(row).file_size)
}

function documentDate(row: unknown): string {
  return formatDate(asDocument(row).created_at)
}

function openDocumentChunks(row: unknown): void {
  void documents.openChunks(asDocument(row))
}

function rebuildDocumentEmbeddings(row: unknown): void {
  void documents.rebuildEmbeddings(asDocument(row))
}

function reprocessDocumentRow(row: unknown): void {
  void documents.reprocess(asDocument(row))
}
</script>

<template>
  <section class="documents-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Knowledge base</p>
        <h2>文档管理</h2>
      </div>
      <div class="header-actions">
        <ElButton :icon="RefreshCw" @click="documents.loadDocuments"
          >刷新</ElButton
        >
        <ElButton
          type="primary"
          :icon="Upload"
          :loading="documents.uploading"
          @click="chooseFile"
        >
          上传文档
        </ElButton>
      </div>
    </header>

    <input
      ref="fileInput"
      class="hidden-input"
      type="file"
      accept=".pdf,.md,.markdown"
      @change="onFileChange"
    />

    <ElProgress
      v-if="documents.uploading"
      :percentage="documents.uploadProgress"
      :stroke-width="10"
    />

    <p v-if="documents.errorMessage" class="page-error">
      {{ documents.errorMessage }}
    </p>

    <ElTable v-loading="documents.loading" :data="documents.documents" stripe>
      <ElTableColumn prop="filename" label="文件名" min-width="220" />
      <ElTableColumn label="状态" width="110">
        <template #default="{ row }">
          <ElTag :type="statusType(row)">
            {{ statusLabel(row) }}
          </ElTag>
        </template>
      </ElTableColumn>
      <ElTableColumn label="大小" width="110">
        <template #default="{ row }">{{ documentSize(row) }}</template>
      </ElTableColumn>
      <ElTableColumn prop="chunk_count" label="切片数" width="90" />
      <ElTableColumn label="上传时间" min-width="180">
        <template #default="{ row }">{{ documentDate(row) }}</template>
      </ElTableColumn>
      <ElTableColumn label="操作" width="310" fixed="right">
        <template #default="{ row }">
          <ElButton
            text
            type="primary"
            :icon="ListTree"
            :disabled="row.status !== 'ready'"
            @click="openDocumentChunks(row)"
          >
            查看切片
          </ElButton>
          <ElButton
            text
            :icon="RefreshCcw"
            :disabled="row.status === 'parsing'"
            @click="rebuildDocumentEmbeddings(row)"
          >
            重建向量
          </ElButton>
          <ElButton
            text
            :icon="RotateCcw"
            :disabled="row.status === 'parsing'"
            @click="reprocessDocumentRow(row)"
          >
            重新解析
          </ElButton>
        </template>
      </ElTableColumn>
    </ElTable>

    <ElDrawer
      :model-value="documents.selectedDocument !== null"
      size="min(46rem, 92vw)"
      title="文档切片"
      @close="documents.closeChunks"
    >
      <p class="drawer-title">{{ documents.selectedDocument?.filename }}</p>
      <article
        v-for="chunk in documents.chunks"
        :key="chunk.chunk_id"
        class="chunk-card"
      >
        <header>
          <strong>#{{ chunk.chunk_index + 1 }}</strong>
          <span v-if="chunk.page_number">第 {{ chunk.page_number }} 页</span>
        </header>
        <p class="heading-path">
          {{
            chunk.heading_path.length
              ? chunk.heading_path.join(' > ')
              : '无标题路径'
          }}
        </p>
        <p class="chunk-content">{{ chunk.content }}</p>
      </article>
    </ElDrawer>
  </section>
</template>

<style scoped>
.documents-page {
  display: grid;
  gap: 1rem;
}

.page-header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 1rem;
}

.page-header h2 {
  margin: 0;
}

.eyebrow {
  margin: 0 0 0.35rem;
  color: #0f766e;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.header-actions {
  display: flex;
  gap: 0.65rem;
}

.hidden-input {
  display: none;
}

.page-error {
  color: #a3302b;
}

.drawer-title {
  margin-top: 0;
  color: #42575d;
}

.chunk-card {
  border: 1px solid #d8e2e3;
  border-radius: 8px;
  margin-bottom: 0.75rem;
  padding: 1rem;
}

.chunk-card header {
  display: flex;
  justify-content: space-between;
  color: #52666b;
}

.heading-path {
  color: #0f766e;
  font-size: 0.82rem;
}

.chunk-content {
  margin-bottom: 0;
  white-space: pre-wrap;
  line-height: 1.65;
}

@media (max-width: 680px) {
  .page-header {
    align-items: stretch;
    flex-direction: column;
  }

  .header-actions {
    justify-content: flex-end;
  }
}
</style>
