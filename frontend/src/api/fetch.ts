import api from './client'

export interface FetchConfig {
  id: string
  sources_enabled: Record<string, boolean> | null
  custom_search_terms: string[] | null
  fetch_frequency: string
  last_fetched_at: string | null
}

export const fetchApi = {
  getConfig: () => api.get<FetchConfig>('/fetch/config'),

  updateConfig: (data: Partial<FetchConfig>) =>
    api.put<FetchConfig>('/fetch/config', data),

  trigger: () => api.post('/fetch/trigger'),

  status: () => api.get('/fetch/status'),
}
