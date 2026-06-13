import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LayoutDashboard, MessageSquare, History, Plus, Trash2, LogOut, Activity, Share2 } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { useSessionStore } from '../../store/sessionStore'
import { useChatStore } from '../../store/chatStore'
import { sessionsApi } from '../../api/sessions'
import toast from 'react-hot-toast'

const NAV = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/chat',      icon: MessageSquare,   label: 'AI Copilot' },
  { to: '/kg',        icon: Share2,          label: 'Knowledge Graph' },
  { to: '/history',   icon: History,         label: 'History' },
]

export default function Sidebar() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const logout = useAuthStore((s) => s.logout)
  const token  = useAuthStore((s) => s.token)
  const user   = useAuthStore((s) => s.user)
  const { activeSessionId, setActiveSession, addSession, removeSession } = useSessionStore()
  const storeSessions = useSessionStore((s) => s.sessions)
  const clearMessages = useChatStore((s) => s.clearMessages)
  const isDemo = token === 'demo-jwt-token-not-real'

  const { data: apiData } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => sessionsApi.list().then((r) => r.data),
    enabled: storeSessions.length === 0 && !isDemo,
    retry: 1,
  })
  const sessions = storeSessions.length > 0 ? storeSessions : (apiData?.sessions || [])

  const createMutation = useMutation({
    mutationFn: () => sessionsApi.create('New session'),
    onSuccess: (res) => {
      addSession(res.data)
      qc.invalidateQueries({ queryKey: ['sessions'] })
      clearMessages()
      navigate(`/chat/${res.data.id}`)
    },
    onError: () => toast.error('Failed to create session'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id) => sessionsApi.delete(id),
    onSuccess: (_, id) => {
      removeSession(id)
      qc.invalidateQueries({ queryKey: ['sessions'] })
      if (activeSessionId === id) { clearMessages(); navigate('/chat') }
    },
    onError: () => toast.error('Failed to delete session'),
  })

  return (
    <aside className="pane-sidebar">

      {/* Wordmark */}
      <div style={{
        height: 48, display: 'flex', alignItems: 'center', gap: 9,
        padding: '0 14px', borderBottom: '1px solid var(--border)', flexShrink: 0,
      }}>
        <div style={{
          width: 22, height: 22, borderRadius: 3,
          background: 'var(--brand)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Activity size={12} color="#fff" strokeWidth={2} />
        </div>
        <div>
          <p className="font-display" style={{ fontSize: 12.5, fontWeight: 800, letterSpacing: '-0.01em', color: 'var(--text-1)', lineHeight: 1.1 }}>
            HealthCopilot
          </p>
          <p className="caption" style={{ fontSize: 9.5, letterSpacing: '0.05em' }}>Data Analyst</p>
        </div>
      </div>

      {/* Navigation */}
      <nav style={{ padding: '12px 8px 8px' }}>
        {NAV.map(({ to, icon: Icon, label }) => {
          const active = pathname.startsWith(to)
          return (
            <Link key={to} to={to} className={`nav-item ${active ? 'active' : ''}`} style={{ textDecoration: 'none' }}>
              <Icon size={14} strokeWidth={1.5} />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* Divider */}
      <div style={{ height: 1, background: 'var(--border)', margin: '4px 14px 12px' }} />

      {/* Sessions */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 14px 8px' }}>
          <span className="overline">Sessions</span>
          <button
            onClick={() => isDemo ? toast('Start the backend to create sessions') : createMutation.mutate()}
            className="btn-ghost"
            title="New session"
          >
            <Plus size={12} strokeWidth={1.5} />
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px' }}>
          {sessions.slice(0, 25).map((s) => (
            <div
              key={s.id}
              className={`session-item ${activeSessionId === s.id ? 'active' : ''}`}
              onClick={() => { setActiveSession(s.id); clearMessages(); navigate(`/chat/${s.id}`) }}
              style={{ justifyContent: 'space-between', cursor: 'pointer' }}
            >
              <span style={{ truncate: true, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {s.title || 'Untitled session'}
              </span>
              <button
                onClick={(e) => { e.stopPropagation(); deleteMutation.mutate(s.id) }}
                className="btn-ghost"
                style={{ opacity: 0, flexShrink: 0 }}
                onMouseEnter={(e) => e.currentTarget.style.opacity = 1}
                onMouseLeave={(e) => e.currentTarget.style.opacity = 0}
              >
                <Trash2 size={10} strokeWidth={1.5} />
              </button>
            </div>
          ))}
          {sessions.length === 0 && (
            <p className="caption" style={{ padding: '12px 6px', textAlign: 'center', lineHeight: 1.6 }}>
              No sessions yet.
            </p>
          )}
        </div>
      </div>

      {/* User / logout */}
      <div style={{ padding: '10px 8px 12px', borderTop: '1px solid var(--border)' }}>
        {user && (
          <div style={{ padding: '6px 10px 8px', marginBottom: 2 }}>
            <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)', lineHeight: 1 }}>{user.username || user.email}</p>
            <p className="caption" style={{ marginTop: 3, textTransform: 'capitalize' }}>{user.role}</p>
          </div>
        )}
        <button
          onClick={() => { logout(); navigate('/login') }}
          className="nav-item"
          style={{ width: '100%', justifyContent: 'flex-start', border: 'none', background: 'none' }}
        >
          <LogOut size={13} strokeWidth={1.5} />
          Sign out
        </button>
      </div>
    </aside>
  )
}
