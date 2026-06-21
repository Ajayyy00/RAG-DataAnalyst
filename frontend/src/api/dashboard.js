import axios from 'axios'

// Auth travels via the HttpOnly cookie (withCredentials) — no Bearer header,
// no token read from JS.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8001/api/v1',
  withCredentials: true,
})

export const dashboardApi = {
  generate: (request) => api.post('/dashboard/generate', { request }),
}
