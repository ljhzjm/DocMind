// Vue 概念：API 层封装上传、列表和切片请求，页面只关心结果。
// Vue 概念：XHR 的 upload.onprogress 可以提供上传进度，fetch 当前不直接提供。
// Vue 概念：AbortSignal 可用于页面离开时取消普通 fetch 请求。

import type {
  DocumentChunk,
  DocumentItem,
  DocumentStatusResponse,
  DocumentUploadResponse,
} from '../types/documents'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(
  /\/$/,
  '',
)
const DOCUMENTS_URL = `${API_BASE_URL}/api/v1/documents`

export async function fetchDocuments(): Promise<DocumentItem[]> {
  const response = await fetch(DOCUMENTS_URL)
  if (!response.ok) {
    throw new Error(`文档列表请求失败：${response.status}`)
  }
  return (await response.json()) as DocumentItem[]
}

export async function fetchDocumentStatus(
  documentId: string,
): Promise<DocumentStatusResponse> {
  const response = await fetch(`${DOCUMENTS_URL}/${documentId}/status`)
  if (!response.ok) {
    throw new Error(`文档状态请求失败：${response.status}`)
  }
  return (await response.json()) as DocumentStatusResponse
}

export async function fetchDocumentChunks(
  documentId: string,
): Promise<DocumentChunk[]> {
  const response = await fetch(`${DOCUMENTS_URL}/${documentId}/chunks`)
  if (!response.ok) {
    throw new Error(`切片列表请求失败：${response.status}`)
  }
  return (await response.json()) as DocumentChunk[]
}

export function uploadDocument(
  file: File,
  onProgress: (percent: number) => void,
): Promise<DocumentUploadResponse> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    const formData = new FormData()
    formData.append('file', file)

    request.open('POST', DOCUMENTS_URL)
    request.upload.onprogress = (event: ProgressEvent) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }
    request.onerror = () => reject(new Error('上传失败，请检查后端服务'))
    request.onload = () => {
      if (request.status < 200 || request.status >= 300) {
        reject(new Error(`上传失败：${request.status}`))
        return
      }
      resolve(JSON.parse(request.responseText) as DocumentUploadResponse)
    }
    request.send(formData)
  })
}
