import api from './axios'

export const chatApi = {
  query: (sessionId, question) =>
    api.post('/chat/query', { session_id: sessionId, question }),

  validate: (sql) => api.post('/chat/validate', { sql }),
}
