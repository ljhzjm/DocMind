import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchDocuments, removeDocument } from '../api/documents'
import type { DocumentItem } from '../types/documents'
import { useDocumentsStore } from './documents'

vi.mock('../api/documents', () => ({
  backfillDocumentEmbeddings: vi.fn(),
  fetchDocumentChunks: vi.fn(),
  fetchDocumentStatus: vi.fn(),
  fetchDocuments: vi.fn(),
  removeDocument: vi.fn(),
  reprocessDocument: vi.fn(),
  uploadDocument: vi.fn(),
}))

const document: DocumentItem = {
  document_id: 'document-1',
  filename: 'policy.md',
  status: 'ready',
  file_type: 'md',
  file_size: 128,
  chunk_count: 2,
  created_at: '2026-09-14T00:00:00Z',
}

describe('documents store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('removes a deleted document from the local list', async () => {
    vi.mocked(fetchDocuments).mockResolvedValue([document])
    vi.mocked(removeDocument).mockResolvedValue()
    const store = useDocumentsStore()
    await store.loadDocuments()

    await store.deleteDocument(document)

    expect(removeDocument).toHaveBeenCalledWith('document-1')
    expect(store.documents).toEqual([])
  })
})
