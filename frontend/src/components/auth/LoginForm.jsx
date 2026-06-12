import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Eye, EyeOff, ArrowRight, Activity, User, Lock, Zap } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { useSessionStore } from '../../store/sessionStore'
import { useChatStore } from '../../store/chatStore'
import { authApi } from '../../api/auth'
import { DEMO_USER, DEMO_TOKEN, DEMO_SESSIONS, DEMO_MESSAGES } from '../../data/mockData'
import toast from 'react-hot-toast'

const DEMO_ACCOUNTS = [
  { label: 'Admin',    email: 'admin@healthcare.com',    password: 'Admin1234!',   role: 'Admin'    },
  { label: 'Doctor',   email: 'doctor@healthcare.com',   password: 'Doctor1234!',  role: 'Clinician'},
  { label: 'Analyst',  email: 'analyst@healthcare.com',  password: 'Analyst1234!', role: 'Analyst'  },
]

export default function LoginForm() {
  const navigate        = useNavigate()
  const login           = useAuthStore((s) => s.login)
  const setSessions     = useSessionStore((s) => s.setSessions)
  const setActiveSession= useSessionStore((s) => s.setActiveSession)
  const loadMessages    = useChatStore((s) => s.loadMessages)
  const [form, setForm] = useState({ email: '', password: '' })
  const [showPw, setShowPw] = useState(false)

  /* ── Quick-fill from demo account tile ─────────────────── */
  const fillAccount = (acc) => {
    setForm({ email: acc.email, password: acc.password })
  }

  /* ── Demo mode (no backend) ────────────────────────────── */
  const handleDemo = () => {
    login(DEMO_USER, DEMO_TOKEN)
    setSessions(DEMO_SESSIONS)
    setActiveSession(DEMO_SESSIONS[0].id)
    loadMessages(DEMO_MESSAGES)
    toast.success('Demo workspace loaded')
    navigate('/chat')
  }

  /* ── Real login ─────────────────────────────────────────── */
  const mutation = useMutation({
    mutationFn: () => authApi.login(form.email, form.password),
    onSuccess: async (res) => {
      const { access_token } = res.data
      const { default: api } = await import('../../api/axios')
      const profile = await api.get('/auth/me', {
        headers: { Authorization: `Bearer ${access_token}` },
      })
      login(profile.data, access_token)
      toast.success(`Welcome back, ${profile.data.first_name || profile.data.email}!`)
      navigate('/chat')
    },
    onError: (err) => {
      const msg = err?.response?.data?.message || 'Invalid credentials — check email & password'
      toast.error(msg)
    },
  })

  return (
    <div style={{
      minHeight: '100vh', background: 'var(--canvas)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: '24px 16px',
    }}>
      <div style={{ width: '100%', maxWidth: 380 }}>

        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 40 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 6,
            background: 'var(--brand)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 0 16px rgba(79,107,234,0.4)',
          }}>
            <Activity size={16} color="#fff" strokeWidth={2} />
          </div>
          <span style={{ fontSize: 15, fontWeight: 800, letterSpacing: '-0.02em', color: 'var(--text-1)' }}>
            HealthCopilot
          </span>
        </div>

        <h1 className="heading-lg" style={{ marginBottom: 6 }}>Sign in</h1>
        <p style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 28, lineHeight: 1.6 }}>
          Access the clinical analytics workspace.
        </p>

        {/* ── Quick-select accounts ──────────────────────────── */}
        <div style={{
          marginBottom: 24, padding: '12px 14px',
          border: '1px solid rgba(79,107,234,0.20)',
          borderRadius: 6, background: 'rgba(79,107,234,0.05)',
        }}>
          <p style={{
            fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
            textTransform: 'uppercase', color: 'var(--brand)', marginBottom: 10,
          }}>
            Click an account to auto-fill
          </p>
          <div style={{ display: 'flex', gap: 6 }}>
            {DEMO_ACCOUNTS.map((acc) => (
              <button
                key={acc.email}
                type="button"
                onClick={() => fillAccount(acc)}
                style={{
                  flex: 1, padding: '8px 4px', borderRadius: 4,
                  border: form.email === acc.email
                    ? '1px solid var(--brand)'
                    : '1px solid var(--border)',
                  background: form.email === acc.email
                    ? 'rgba(79,107,234,0.12)'
                    : 'var(--surface)',
                  cursor: 'pointer', transition: 'all 0.15s ease',
                }}
                onMouseEnter={e => { if (form.email !== acc.email) e.currentTarget.style.borderColor = 'rgba(79,107,234,0.4)' }}
                onMouseLeave={e => { if (form.email !== acc.email) e.currentTarget.style.borderColor = 'var(--border)' }}
              >
                <p style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-1)', marginBottom: 2 }}>
                  {acc.label}
                </p>
                <p style={{ fontSize: 9, color: 'var(--text-3)', fontFamily: '"JetBrains Mono",monospace' }}>
                  {acc.role}
                </p>
              </button>
            ))}
          </div>
        </div>

        {/* ── Login form ─────────────────────────────────────── */}
        <form
          onSubmit={(e) => { e.preventDefault(); mutation.mutate() }}
          style={{ display: 'flex', flexDirection: 'column', gap: 14 }}
        >
          {/* Email */}
          <div>
            <label className="field-label" htmlFor="email-input">Email address</label>
            <div style={{ position: 'relative' }}>
              <User
                size={13} strokeWidth={1.5}
                style={{
                  position: 'absolute', left: 11, top: '50%',
                  transform: 'translateY(-50%)', color: 'var(--text-3)',
                  pointerEvents: 'none',
                }}
              />
              <input
                id="email-input"
                type="email"
                required
                autoComplete="email"
                className="field-input"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                placeholder="you@hospital.org"
                style={{ paddingLeft: 32 }}
              />
            </div>
          </div>

          {/* Password */}
          <div>
            <label className="field-label" htmlFor="password-input">Password</label>
            <div style={{ position: 'relative' }}>
              <Lock
                size={13} strokeWidth={1.5}
                style={{
                  position: 'absolute', left: 11, top: '50%',
                  transform: 'translateY(-50%)', color: 'var(--text-3)',
                  pointerEvents: 'none',
                }}
              />
              <input
                id="password-input"
                type={showPw ? 'text' : 'password'}
                required
                autoComplete="current-password"
                className="field-input"
                value={form.password}
                onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                placeholder="••••••••••"
                style={{ paddingLeft: 32, paddingRight: 38 }}
              />
              <button
                type="button"
                onClick={() => setShowPw(!showPw)}
                className="btn-ghost"
                style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)' }}
              >
                {showPw ? <EyeOff size={13} strokeWidth={1.5} /> : <Eye size={13} strokeWidth={1.5} />}
              </button>
            </div>
          </div>

          {/* Credentials hint */}
          {form.email && form.password && (
            <div style={{
              fontSize: 11, color: 'var(--text-3)', padding: '6px 10px',
              background: 'var(--surface-3)', borderRadius: 4,
              fontFamily: '"JetBrains Mono",monospace',
            }}>
              {form.email} / {showPw ? form.password : '•'.repeat(form.password.length)}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={mutation.isPending || !form.email || !form.password}
            className="btn btn-primary"
            style={{ width: '100%', marginTop: 4, fontSize: 13 }}
          >
            {mutation.isPending
              ? 'Signing in…'
              : <><span>Sign in</span> <ArrowRight size={13} strokeWidth={2} /></>
            }
          </button>
        </form>

        {/* Divider */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '24px 0' }}>
          <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
          <span className="caption">or</span>
          <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
        </div>

        {/* Demo button */}
        <button onClick={handleDemo} className="btn btn-outline" style={{ width: '100%' }}>
          <Zap size={13} strokeWidth={1.5} />
          Launch demo workspace (no backend)
        </button>

        {/* Credentials reference */}
        <div style={{
          marginTop: 24, padding: '10px 12px', borderRadius: 4,
          border: '1px solid var(--border)', background: 'var(--surface)',
        }}>
          <p style={{
            fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
            textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: 6,
          }}>Test credentials</p>
          {DEMO_ACCOUNTS.map(acc => (
            <div key={acc.email} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
              <span style={{ fontSize: 10, color: 'var(--text-2)', fontFamily: '"JetBrains Mono",monospace' }}>
                {acc.email}
              </span>
              <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: '"JetBrains Mono",monospace' }}>
                {acc.password}
              </span>
            </div>
          ))}
        </div>

        <p className="caption" style={{ marginTop: 20, textAlign: 'center' }}>
          Healthcare Data Analyst Copilot — v1.0
        </p>
      </div>
    </div>
  )
}
