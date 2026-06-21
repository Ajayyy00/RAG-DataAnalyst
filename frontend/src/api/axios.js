import axios from 'axios'
import { useAuthStore } from '../store/authStore'

// withCredentials makes the browser send/receive the HttpOnly auth cookies.
// Tokens are NEVER stored in JS (no localStorage) — they live only in cookies
// that JavaScript cannot read, which neutralizes XSS token theft.
const api = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

let refreshing = null

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    const status = err.response?.status

    // On a 401, try a single silent refresh (cookie-based) then replay once.
    if (status === 401 && original && !original._retry && !original._isAuth) {
      original._retry = true
      try {
        refreshing = refreshing || api.post('/auth/refresh', {}, { _isAuth: true })
        await refreshing
        refreshing = null
        return api(original)
      } catch (e) {
        refreshing = null
        useAuthStore.getState().logout()
        if (window.location.pathname !== '/login') window.location.href = '/login'
        return Promise.reject(e)
      }
    }

    if (status === 401) {
      useAuthStore.getState().logout()
      if (window.location.pathname !== '/login') window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api
