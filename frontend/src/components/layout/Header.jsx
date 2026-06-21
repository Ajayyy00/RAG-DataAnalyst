import { useLocation } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

const PAGE = {
  '/chat':      'AI Copilot',
  '/dashboard': 'Dashboard',
  '/history':   'History',
}

export default function Header() {
  const { pathname } = useLocation()
  const user  = useAuthStore((s) => s.user)
  const isDemo = user?.id === 'demo-user-001'
  const title = Object.entries(PAGE).find(([p]) => pathname.startsWith(p))?.[1] || 'Copilot'

  return (
    <header className="pane-header">
      {/* Left */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <h1 className="font-display" style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)', letterSpacing: '-0.01em' }}>
          {title}
        </h1>
        {isDemo && (
          <span style={{
            fontSize: 9.5,
            fontFamily: "'Plus Jakarta Sans', sans-serif",
            fontWeight: 700,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'var(--brand)',
            background: 'var(--brand-dim)',
            border: '1px solid var(--brand-border)',
            borderRadius: 2,
            padding: '2px 7px',
          }}>
            Demo
          </span>
        )}
      </div>

      {/* Right — user pill */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{
          width: 26, height: 26, borderRadius: 3,
          background: 'var(--surface-3)',
          border: '1px solid var(--border-2)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: "'Plus Jakarta Sans', sans-serif",
          fontSize: 11, fontWeight: 800,
          color: 'var(--brand)',
        }}>
          {user?.username?.[0]?.toUpperCase() || 'U'}
        </div>
        <div>
          <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)', lineHeight: 1 }}>
            {user?.username || 'User'}
          </p>
          <p className="caption" style={{ marginTop: 2, textTransform: 'capitalize' }}>
            {user?.role || 'analyst'}
          </p>
        </div>
      </div>
    </header>
  )
}
