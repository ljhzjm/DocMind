// Vue 概念：Pinia store 统一维护文档列表、上传进度和切片抽屉状态。
// Vue 概念：action 可以串联上传、刷新和轮询，组件只调用一个方法。
// Vue 概念：onUnmounted 时停止定时器，避免页面离开后继续请求。

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  fetchDocumentChunks,
  fetchDocuments,
  fetchDocumentStatus,
  uploadDocument,
} from '../api/documents'
import type {
  DocumentChunk,
  DocumentItem,
  DocumentStatus,
} from '../types/documents'

const ACTIVE_STATUSES = new Set<DocumentStatus>(['uploaded', 'parsing'])

export const useDocumentsStore = defineStore('documents', () => {
  const documents = ref<DocumentItem[]>([])
  const chunks = ref<DocumentChunk[]>([])
  const selectedDocument = ref<DocumentItem | null>(null)
  const loading = ref(false)
  const uploading = ref(false)
  const uploadProgress = ref(0)
  const errorMessage = ref('')
  let pollingTimer: ReturnType<typeof setInterval> | null = null

  const hasActiveDocuments = computed(() =>
    documents.value.some((document) => ACTIVE_STATUSES.has(document.status)),
  )

  async function loadDocuments(): Promise<void> {
    loading.value = true
    errorMessage.value = ''
    try {
      documents.value = await fetchDocuments()
      syncPolling()
    } catch (error: unknown) {
      errorMessage.value = error instanceof Error ? error.message : '加载失败'
    } finally {
      loading.value = false
    }
  }

  async function upload(file: File): Promise<void> {
    uploading.value = true
    uploadProgress.value = 0
    errorMessage.value = ''
    try {
      await uploadDocument(file, (percent) => {
        uploadProgress.value = percent
      })
      await loadDocuments()
    } catch (error: unknown) {
      errorMessage.value = error instanceof Error ? error.message : '上传失败'
    } finally {
      uploading.value = false
    }
  }

  async function refreshActiveDocuments(): Promise<void> {
    const activeDocuments = documents.value.filter((document) =>
      ACTIVE_STATUSES.has(document.status),
    )
    await Promise.all(
      activeDocuments.map(async (document) => {
        const response = await fetchDocumentStatus(document.document_id)
        document.status = response.status
        document.chunk_count = response.chunk_count
      }),
    )
    syncPolling()
  }

  async function openChunks(document: DocumentItem): Promise<void> {
    selectedDocument.value = document
    chunks.value = []
    try {
      chunks.value = await fetchDocumentChunks(document.document_id)
    } catch (error: unknown) {
      errorMessage.value =
        error instanceof Error ? error.message : '切片加载失败'
    }
  }

  function closeChunks(): void {
    selectedDocument.value = null
    chunks.value = []
  }

  function syncPolling(): void {
    if (!hasActiveDocuments.value || pollingTimer !== null) {
      return
    }
    pollingTimer = setInterval(() => {
      void refreshActiveDocuments()
    }, 2000)
  }

  function stopPolling(): void {
    if (pollingTimer !== null) {
      clearInterval(pollingTimer)
      pollingTimer = null
    }
  }

  return {
    documents,
    chunks,
    selectedDocument,
    loading,
    uploading,
    uploadProgress,
    errorMessage,
    hasActiveDocuments,
    loadDocuments,
    upload,
    openChunks,
    closeChunks,
    stopPolling,
  }
})
