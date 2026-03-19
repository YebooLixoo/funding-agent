import api from './client'

export interface Keyword {
  id: string
  keyword: string
  category: string
  source: string
  weight: number
  is_active: boolean
  created_at: string
}

export interface KeywordsByCategory {
  primary: Keyword[]
  domain: Keyword[]
  career: Keyword[]
  faculty: Keyword[]
  exclusion: Keyword[]
  custom: Keyword[]
}

export interface KeywordCreate {
  keyword: string
  category: string
  source?: string
  weight?: number
}

export const keywordsApi = {
  list: () => api.get<KeywordsByCategory>('/keywords'),

  add: (data: KeywordCreate) => api.post<Keyword>('/keywords', data),

  update: (id: string, data: Partial<KeywordCreate & { is_active: boolean }>) =>
    api.put<Keyword>(`/keywords/${id}`, data),

  remove: (id: string) => api.delete(`/keywords/${id}`),

  bulkAdd: (keywords: KeywordCreate[]) =>
    api.post<Keyword[]>('/keywords/bulk', { keywords }),
}

export const filterSettingsApi = {
  get: () => api.get('/filter-settings'),

  update: (data: {
    keyword_threshold?: number
    llm_threshold?: number
    use_llm_filter?: boolean
    sources_enabled?: Record<string, boolean>
  }) => api.put('/filter-settings', data),
}

export const scoringApi = {
  rescore: () => api.post('/scoring/rescore'),
}
