import api from './axios'

// All auth tokens are delivered as HttpOnly cookies by the backend, so the
// frontend never handles raw tokens. `_isAuth: true` marks calls the axios
// interceptor must not try to auto-refresh (prevents loops).
export const authApi = {
  login: (email, password) =>
    api.post('/auth/login', new URLSearchParams({ username: email, password }), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      _isAuth: true,
    }),

  register: (data) => api.post('/auth/register', data),

  me: () => api.get('/auth/me'),

  // Cookie carries the refresh token; no body needed.
  refresh: () => api.post('/auth/refresh', {}, { _isAuth: true }),

  logout: () => api.post('/auth/logout'),

  changePassword: (data) => api.post('/auth/change-password', data),
}
