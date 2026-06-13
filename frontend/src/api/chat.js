import api from './axios'

export const chatApi = {
  query: async (sessionId, question, onProgress) => {
    const authStorage = localStorage.getItem('hc-auth')
    const token = authStorage ? JSON.parse(authStorage).state.token : ''
    
    // Default to the correct backend host/port
    const apiUrl = '/api/v1'
    
    const res = await fetch(`${apiUrl}/chat/query-agentic`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ session_id: sessionId, question })
    })

    if (!res.ok) {
      let detail = ''
      try { detail = await res.text() } catch (_) {}
      throw new Error(`API error ${res.status}: ${detail || res.statusText}`)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let resultData = null
    let buffer = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      
      const lines = buffer.split('\n\n')
      buffer = lines.pop() // keep incomplete chunk
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          let data
          try {
            data = JSON.parse(line.slice(6))
          } catch (e) {
            console.error('Failed to parse SSE line', line, e)
            continue
          }
          if (data.type === 'progress') {
            if (onProgress) onProgress(data.agent)
          } else if (data.type === 'result') {
            resultData = data.data
          } else if (data.type === 'error') {
            throw new Error(data.message || 'Query failed in the multi-agent pipeline.')
          }
        }
      }
    }
    return resultData
  },

  validate: (sql) => api.post('/chat/validate', { sql }),
}
