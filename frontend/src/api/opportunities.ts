import api from './client'

export interface Opportunity {
  id: string
  composite_id: string
  source: string
  source_id: string
  title: string
  description: string | null
  url: string | null
  source_type: string | null
  deadline: string | null
  posted_date: string | null
  funding_amount: string | null
  keywords: string[] | null
  summary: string | null
  opportunity_status: string
  deadline_type: string
  // Compute resource fields
  resource_type: string | null
  resource_provider: string | null
  resource_scale: string | null
  allocation_details: string | null
  eligibility: string | null
  access_url: string | null
  fetched_at: string
  relevance_score: number | null
  keyword_score: number | null
  profile_score: number | null
  behavior_score: number | null
  urgency_score: number | null
  matched_keywords: string[] | null
  is_bookmarked: boolean
  is_dismissed: boolean
}

export interface OpportunityListResponse {
  items: Opportunity[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface OpportunityFilters {
  page?: number
  page_size?: number
  source?: string
  source_type?: string
  opportunity_status?: string
  search?: string
  min_score?: number
  sort_by?: string
  sort_order?: string
}

export const opportunitiesApi = {
  list: (filters: OpportunityFilters = {}) =>
    api.get<OpportunityListResponse>('/opportunities', { params: filters }),

  get: (id: string) =>
    api.get<Opportunity>(`/opportunities/${id}`),

  bookmark: (id: string) =>
    api.post(`/opportunities/${id}/bookmark`),

  unbookmark: (id: string) =>
    api.delete(`/opportunities/${id}/bookmark`),

  dismiss: (id: string) =>
    api.post(`/opportunities/${id}/dismiss`),

  listBookmarks: () =>
    api.get<Opportunity[]>('/opportunities/bookmarks/list'),
}
