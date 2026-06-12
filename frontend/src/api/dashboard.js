import axios from 'axios'
import { useAuthStore } from '../store/authStore'

const api = () => axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8001/api/v1',
  headers: { Authorization: `Bearer ${useAuthStore.getState().token}` },
})

export const dashboardApi = {
  generate: (request) => api().post('/dashboard/generate', { request }),
}
