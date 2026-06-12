import { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useChatStore } from '../store/chatStore'
import { useSessionStore } from '../store/sessionStore'
import { useAuthStore } from '../store/authStore'
import { chatApi } from '../api/chat'
import { sessionsApi } from '../api/sessions'
import ChatPanel from '../components/chat/ChatPanel'
import toast from 'react-hot-toast'

export default function Chat() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const token = useAuthStore((s) => s.token)

  const { messages, isStreaming, addUserMessage, addAssistantMessage, setStreaming, clearMessages, loadMessages } = useChatStore()
  const { activeSessionId, setActiveSession, addSession } = useSessionStore()

  const isDemo = token === 'demo-jwt-token-not-real'

  // Load session messages from API — disabled in demo mode
  const { data: sessionData } = useQuery({
    queryKey: ['session-messages', sessionId],
    queryFn: () => sessionsApi.getMessages(sessionId).then((r) => r.data),
    enabled: !!sessionId && !isDemo,
    retry: 0,
  })

  useEffect(() => {
    if (sessionId) {
      setActiveSession(sessionId)
    }
  }, [sessionId])

  useEffect(() => {
    if (sessionData?.messages) {
      const toNum = (v) => {
        if (v === null || v === undefined || v === '') return v
        const n = Number(v)
        return isFinite(n) ? n : v
      }
      const rowsToObjects = (columns, rows) =>
        (rows || []).map(row => {
          const obj = {}
          ;(columns || []).forEach((col, i) => {
            const v = row[i]
            obj[col] = typeof v === 'string' ? toNum(v) : (v === undefined ? null : v)
          })
          return obj
        })

      const mapped = sessionData.messages.map((m) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        timestamp: m.created_at,
        sql: m.generated_sql,
        columns: m.result_data?.columns,
        rows: m.result_data?.rows,
        rowCount: m.result_data?.row_count,
        chartType: m.chart_config?.chart_type || m.chart_config?.type,
        chartConfig: m.chart_config ? {
          xKey:        m.chart_config.x_key,
          yKey:        m.chart_config.y_key,
          series_keys: m.chart_config.series_keys || [m.chart_config.y_key].filter(Boolean),
          title:       m.chart_config.title,
          data:        rowsToObjects(m.result_data?.columns, m.result_data?.rows),
        } : undefined,
        insights: m.insights,
        insightReport: m.insight_report,
      }))
      loadMessages(mapped)
    }
  }, [sessionData])

  // Create session + run REST query mutation
  const queryMutation = useMutation({
    mutationFn: async (question) => {
      let sid = activeSessionId || sessionId
      // Auto-create session if none active
      if (!sid) {
        const res = await sessionsApi.create(question.slice(0, 60))
        const newSession = res.data
        addSession(newSession)
        sid = newSession.id
        qc.invalidateQueries({ queryKey: ['sessions'] })
        navigate(`/chat/${sid}`, { replace: true })
      }
      return chatApi.query(sid, question).then((r) => r.data)
    },
    onSuccess: (data) => {
      const toNum = (v) => {
        if (v === null || v === undefined || v === '') return v
        const n = Number(v)
        return isFinite(n) ? n : v
      }
      const rowsToObjects = (columns, rows) =>
        (rows || []).map(row => {
          const obj = {}
          ;(columns || []).forEach((col, i) => {
            const v = row[i]
            obj[col] = typeof v === 'string' ? toNum(v) : (v === undefined ? null : v)
          })
          return obj
        })

      const chart = data.chart
      addAssistantMessage({
        sql:        data.sql?.generated,
        isValid:    data.sql?.validated,
        columns:    data.results?.columns,
        rows:       data.results?.rows,
        rowCount:   data.results?.row_count,
        chartType:  chart?.type,
        chartConfig: chart ? {
          xKey:        chart.x_key,
          yKey:        chart.y_key,
          series_keys: chart.series_keys || [chart.y_key].filter(Boolean),
          title:       chart.title,
          data:        rowsToObjects(data.results?.columns, data.results?.rows),
        } : undefined,
        insights:      data.insights,
        insightReport: data.insight_report,
      })
    },
    onError: (err) => {
      const msg = err.response?.data?.message || 'Query failed. Please try again.'
      addAssistantMessage({ error: msg })
      toast.error(msg)
    },
  })

  const handleSend = (question) => {
    addUserMessage(question)
    setStreaming(true, 'Generating SQL...')
    queryMutation.mutate(question)
  }

  return (
    <div className="h-full flex flex-col">
      <ChatPanel onSend={handleSend} />
    </div>
  )
}
