import api from './axios'

export const sessionsApi = {
  list: () => api.get('/sessions'),
  create: (title) => api.post('/sessions', { title }),
  get: (id) => api.get(`/sessions/${id}`),
  delete: (id) => api.delete(`/sessions/${id}`),
  getMessages: (id) => api.get(`/sessions/${id}/messages`),
}
