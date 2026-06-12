import api from './axios'

export const authApi = {
  login: (email, password) =>
    api.post('/auth/login', new URLSearchParams({ username: email, password }), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }),

  register: (data) => api.post('/auth/register', data),

  me: () => api.get('/auth/me'),

  refresh: (refreshToken) =>
    api.post('/auth/refresh', { refresh_token: refreshToken }),

  changePassword: (data) => api.post('/auth/change-password', data),
}
