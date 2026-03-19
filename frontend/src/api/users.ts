import api from './client'

export interface UserUpdate {
  full_name?: string
  institution?: string
  department?: string
  position?: string
  research_summary?: string
}

export const usersApi = {
  getMe: () => api.get('/users/me'),
  updateMe: (data: UserUpdate) => api.put('/users/me', data),
}
