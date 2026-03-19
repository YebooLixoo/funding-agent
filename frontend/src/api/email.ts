import api from './client'

export interface EmailPref {
  id: string
  is_subscribed: boolean
  frequency: string
  day_of_week: number
  time_of_day: string
  min_relevance_score: number
  deadline_lookahead_days: number
  last_sent_at: string | null
}

export interface EmailHistory {
  id: string
  sent_at: string
  opportunity_count: number
  success: boolean
  error_msg: string | null
}

export const emailApi = {
  getPreferences: () => api.get<EmailPref>('/email/preferences'),

  updatePreferences: (data: Partial<EmailPref>) =>
    api.put<EmailPref>('/email/preferences', data),

  unsubscribe: () => api.post('/email/unsubscribe'),

  history: () => api.get<EmailHistory[]>('/email/history'),

  sendTest: () => api.post('/email/send-test'),
}
