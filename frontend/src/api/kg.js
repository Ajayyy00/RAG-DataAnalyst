import api from './axios'

export const kgApi = {
  /** Trigger ETL sync: Postgres → Neo4j */
  sync: () => api.post('/kg/sync'),

  /** Natural language → Cypher → LLM answer */
  query: (question) => api.post('/kg/query', { question }),

  /** Node / relationship stats */
  stats: () => api.get('/kg/stats'),
}
