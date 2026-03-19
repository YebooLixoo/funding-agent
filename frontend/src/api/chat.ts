import api from './client'

export interface ChatResponse {
  reply: string
  session_id: string
  suggested_actions: { actions: Action[] } | null
}

export interface Action {
  type: 'add' | 'remove' | 'update'
  keyword: string
  category: string
  weight?: number
}

export interface ChatMessage {
  id: string
  session_id: string
  role: string
  content: string
  suggested_actions: { actions: Action[] } | null
  actions_applied: boolean
  created_at: string
}

export const chatApi = {
  send: (message: string, sessionId?: string) =>
    api.post<ChatResponse>('/chat', { message, session_id: sessionId }),

  history: (sessionId?: string) =>
    api.get<ChatMessage[]>('/chat/history', { params: sessionId ? { session_id: sessionId } : {} }),

  applyActions: (messageId: string) =>
    api.post('/chat/apply-actions', { message_id: messageId }),
}
