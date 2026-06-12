import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { useSessionStore } from '../store/sessionStore'
import { sessionsApi } from '../api/sessions'
import { Spinner } from '../components/ui/Spinner'
import { MessageSquare, ArrowRight } from 'lucide-react'

export default function History() {
  const navigate = useNavigate()
  const token = useAuthStore((s) => s.token)
  const storeSessions = useSessionStore((s) => s.sessions)
  const isDemo = token === 'demo-jwt-token-not-real'

  const { data, isLoading } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => sessionsApi.list().then((r) => r.data),
    enabled: !isDemo,
    retry: 1,
  })

  const sessions = isDemo ? storeSessions : (data?.sessions || [])

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '32px 36px' }}>

      {/* Heading */}
      <div style={{ marginBottom: 32 }}>
        <h1 className="heading-lg">History</h1>
        <p style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 6 }}>
          All query sessions, most recent first.
        </p>
      </div>

      {/* Session table */}
      <div style={{ border: '1px solid var(--border)', borderRadius: 4, background: 'var(--surface)', maxWidth: 720 }}>
        {/* Table header */}
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 120px 32px',
          padding: '8px 16px', borderBottom: '1px solid var(--border)',
          background: 'var(--surface-2)',
        }}>
          <span className="overline">Session title</span>
          <span className="overline" style={{ textAlign: 'right' }}>Created</span>
          <span />
        </div>

        {/* Rows */}
        {isLoading && !isDemo ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
            <Spinner />
          </div>
        ) : sessions.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, padding: '48px 0' }}>
            <MessageSquare size={20} strokeWidth={1.5} style={{ color: 'var(--text-3)' }} />
            <p className="caption">No sessions yet. Start a query in AI Copilot.</p>
          </div>
        ) : (
          sessions.map((s, i) => (
            <div
              key={s.id}
              onClick={() => navigate(`/chat/${s.id}`)}
              style={{
                display: 'grid', gridTemplateColumns: '1fr 120px 32px',
                alignItems: 'center',
                padding: '11px 16px',
                borderBottom: i < sessions.length - 1 ? '1px solid var(--border)' : 'none',
                cursor: 'pointer',
                transition: 'background 150ms ease-in-out',
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'var(--hover)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
            >
              <p style={{
                fontSize: 13, color: 'var(--text-1)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', paddingRight: 16,
              }}>
                {s.title || 'Untitled session'}
              </p>
              <p style={{
                fontSize: 11, color: 'var(--text-3)', textAlign: 'right',
                fontFamily: '"JetBrains Mono", monospace',
              }}>
                {new Date(s.created_at).toLocaleDateString()}
              </p>
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <ArrowRight size={12} strokeWidth={1.5} style={{ color: 'var(--text-3)' }} />
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
