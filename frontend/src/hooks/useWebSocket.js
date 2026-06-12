import { useEffect, useRef, useCallback } from 'react'
import { useAuthStore } from '../store/authStore'
import { useChatStore } from '../store/chatStore'

export function useWebSocket(sessionId) {
  const ws = useRef(null)
  const token = useAuthStore((s) => s.token)
  const { setStreaming, addAssistantMessage } = useChatStore()

  const connect = useCallback(() => {
    if (!sessionId || !token) return
    const url = `ws://localhost:8001/api/v1/stream/${sessionId}?token=${token}`
    ws.current = new WebSocket(url)

    const result = {}

    ws.current.onopen = () => setStreaming(true, 'Connecting...')

    ws.current.onmessage = (e) => {
      const event = JSON.parse(e.data)
      switch (event.type) {
        case 'status':
          setStreaming(true, event.payload.step)
          break
        case 'sql_generated':
          result.sql = event.payload.sql
          setStreaming(true, 'Validating SQL...')
          break
        case 'sql_validated':
          result.isValid = event.payload.is_valid
          setStreaming(true, 'Executing query...')
          break
        case 'results_ready':
          result.columns = event.payload.columns
          result.rows = event.payload.rows
          result.rowCount = event.payload.row_count
          setStreaming(true, 'Generating chart...')
          break
        case 'chart_ready':
          result.chartType = event.payload.chart_type
          result.chartConfig = event.payload.chart_config
          setStreaming(true, 'Generating insights...')
          break
        case 'insights_ready':
          result.insights = event.payload.insights
          setStreaming(true, 'Finalising...')
          break
        case 'done':
          addAssistantMessage(result)
          ws.current?.close()
          break
        case 'error':
          addAssistantMessage({ error: event.payload.message })
          ws.current?.close()
          break
        default:
          break
      }
    }

    ws.current.onerror = () => {
      setStreaming(false)
    }

    ws.current.onclose = () => setStreaming(false)
  }, [sessionId, token])

  const disconnect = useCallback(() => {
    ws.current?.close()
  }, [])

  useEffect(() => {
    return () => ws.current?.close()
  }, [])

  return { connect, disconnect }
}
