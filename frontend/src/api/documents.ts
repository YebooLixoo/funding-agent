import api from './client'

export interface Document {
  id: string
  filename: string
  file_type: string
  upload_status: string
  extracted_keywords: Record<string, string[]> | null
  created_at: string
}

export interface DocumentDetail extends Document {
  extracted_text: string | null
}

export const documentsApi = {
  list: () => api.get<Document[]>('/documents'),

  get: (id: string) => api.get<DocumentDetail>(`/documents/${id}`),

  upload: (file: File, fileType: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('file_type', fileType)
    return api.post<Document>('/documents', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  remove: (id: string) => api.delete(`/documents/${id}`),

  reprocess: (id: string) => api.post<Document>(`/documents/${id}/reprocess`),
}
