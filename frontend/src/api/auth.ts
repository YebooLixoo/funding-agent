import api from './client'

export interface RegisterData {
  email: string
  password: string
  full_name: string
  institution?: string
  department?: string
  position?: string
  research_summary?: string
}

export interface LoginData {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export const authApi = {
  register: (data: RegisterData) =>
    api.post<TokenResponse>('/auth/register', data),

  login: (data: LoginData) =>
    api.post<TokenResponse>('/auth/login', data),

  getMe: () => api.get('/users/me'),
}
