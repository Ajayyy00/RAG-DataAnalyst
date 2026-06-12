import { useState, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  BarChart2, TrendingUp, PieChart, Activity, Sparkles,
  AlertCircle, ChevronDown, ChevronUp, Send, LayoutDashboard,
  Database, Layers,
} from 'lucide-react'
import {
  BarChart, Bar, LineChart, Line, AreaChart, Area,
  PieChart as RechartsPie, Pie, Cell,
  ScatterChart, Scatter,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { dashboardApi } from '../api/dashboard'
import toast from 'react-hot-toast'

/* ── Palette ─────────────────────────────────────────────── */
const BRAND   = '#4F6BEA'
const COLORS  = ['#4F6BEA','#0EA861','#F59E0B','#E05858','#8B5CF6','#06B6D4','#F97316']
const AXIS_STYLE = {
  tick: { fontSize: 9, fontFamily: '"JetBrains Mono",monospace', fill: '#38455A' },
  axisLine: { stroke: 'rgba(255,255,255,0.06)' },
  tickLine: false,
}

/* ── Helpers ─────────────────────────────────────────────── */
const fmtVal = (v) => {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (!isNaN(n) && typeof v !== 'boolean' && String(v).trim() !== '') {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
    if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K'
    if (n % 1 !== 0)    return n.toLocaleString(undefined, { maximumFractionDigits: 2 })
    return n.toLocaleString()
  }
  return String(v)
}

/* ── Suggested prompts ───────────────────────────────────── */
const SUGGESTIONS = [
  'Show hospital admissions trends',
  'Analyse readmission patterns by department',
  'Top diagnoses and medication usage',
  'Lab result abnormalities overview',
  'Provider performance metrics',
  'Emergency vs inpatient encounter breakdown',
]

/* ── Custom Tooltip ─────────────────────────────────────── */
function Tip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: '#161A26', border: '1px solid rgba(255,255,255,0.10)',
      padding: '8px 12px', borderRadius: 3, fontSize: 11,
    }}>
      {label && <p style={{ color: '#6E7D96', marginBottom: 4, fontSize: 10 }}>{label}</p>}
      {payload.map((p, i) => (
        <div key={i} style={{ display: 'flex', gap: 10, justifyContent: 'space-between' }}>
          <span style={{ color: '#6E7D96' }}>{p.name || p.dataKey}</span>
          <span style={{ color: p.color || BRAND, fontFamily: '"JetBrains Mono",monospace', fontWeight: 500 }}>
            {fmtVal(p.value)}
          </span>
        </div>
      ))}
    </div>
  )
}

/* ── Mini chart renderers ───────────────────────────────── */
function PanelChart({ panel }) {
  const { chart_type, chart_data, x_key, y_key, series_keys, columns } = panel
  const yK = y_key || series_keys?.[0] || columns?.[1] || 'value'
  const xK = x_key || columns?.[0] || 'name'

  if (!chart_data?.length) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center',
                    height: 160, color: 'var(--text-3)', fontSize: 11 }}>
        No data returned
      </div>
    )
  }

  const h = 160

  if (chart_type === 'kpi') {
    const val = chart_data[0]?.[yK] ?? chart_data[0]?.[xK] ?? '—'
    const label = chart_data[0]?.[xK] || yK
    return (
      <div style={{ height: h, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <p style={{ fontFamily: '"JetBrains Mono",monospace', fontSize: 48, fontWeight: 600, color: 'var(--text-1)', lineHeight: 1, margin: 0 }}>
          {fmtVal(val)}
        </p>
        {label && <p style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 12, textTransform: 'capitalize' }}>{String(label).replace(/_/g, ' ')}</p>}
      </div>
    )
  }

  if (chart_type === 'pie') {
    return (
      <ResponsiveContainer width="100%" height={h}>
        <RechartsPie>
          <Pie data={chart_data} dataKey={yK} nameKey={xK} cx="50%" cy="50%"
               innerRadius={40} outerRadius={70} paddingAngle={2}>
            {chart_data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
          </Pie>
          <Tooltip content={<Tip />} />
        </RechartsPie>
      </ResponsiveContainer>
    )
  }

  if (chart_type === 'scatter') {
    return (
      <ResponsiveContainer width="100%" height={h}>
        <ScatterChart margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
          <XAxis dataKey={xK} tickFormatter={fmtVal} {...AXIS_STYLE} />
          <YAxis dataKey={yK} tickFormatter={fmtVal} {...AXIS_STYLE} />
          <Tooltip content={<Tip />} />
          <Scatter data={chart_data} fill={BRAND} opacity={0.7} />
        </ScatterChart>
      </ResponsiveContainer>
    )
  }

  if (chart_type === 'line' || chart_type === 'area') {
    return (
      <ResponsiveContainer width="100%" height={h}>
        <AreaChart data={chart_data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={`aFill${panel.id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={BRAND} stopOpacity={0.15} />
              <stop offset="100%" stopColor={BRAND} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
          <XAxis dataKey={xK} {...AXIS_STYLE} />
          <YAxis tickFormatter={fmtVal} width={40} {...AXIS_STYLE} />
          <Tooltip content={<Tip />} />
          <Area type="monotone" dataKey={yK} stroke={BRAND} strokeWidth={1.5}
                fill={`url(#aFill${panel.id})`}
                dot={{ r: 2.5, fill: BRAND, strokeWidth: 0 }} activeDot={{ r: 4 }} />
        </AreaChart>
      </ResponsiveContainer>
    )
  }

  if (chart_type === 'heatmap') {
    // Render as table heatmap
    const maxVal = Math.max(...chart_data.map(d => Number(d[yK]) || 0))
    return (
      <div style={{ overflowX: 'auto', height: h, overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
          <thead>
            <tr>{panel.columns.map(c => (
              <th key={c} style={{ padding: '4px 8px', color: 'var(--text-3)',
                                   textAlign: 'left', borderBottom: '1px solid var(--border)',
                                   fontFamily: '"JetBrains Mono",monospace' }}>{c}</th>
            ))}</tr>
          </thead>
          <tbody>
            {panel.rows.slice(0, 10).map((row, ri) => (
              <tr key={ri}>
                {row.map((cell, ci) => {
                  const num = Number(cell)
                  const intensity = !isNaN(num) && maxVal > 0 ? num / maxVal : 0
                  return (
                    <td key={ci} style={{
                      padding: '4px 8px', fontSize: 10,
                      color: 'var(--text-2)', borderBottom: '1px solid rgba(255,255,255,0.03)',
                      background: !isNaN(num) && cell !== '' && cell !== null ? `rgba(79,107,234,${intensity * 0.35})` : 'transparent',
                      fontFamily: ci > 0 ? '"JetBrains Mono",monospace' : undefined,
                    }}>{fmtVal(cell)}</td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (chart_type === 'table') {
    return (
      <div style={{ overflowX: 'auto', height: h, overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
          <thead>
            <tr>{panel.columns.map(c => (
              <th key={c} style={{ padding: '4px 8px', color: 'var(--text-3)',
                                   textAlign: 'left', borderBottom: '1px solid var(--border)',
                                   fontFamily: '"JetBrains Mono",monospace' }}>{c}</th>
            ))}</tr>
          </thead>
          <tbody>
            {panel.rows.slice(0, 8).map((row, ri) => (
              <tr key={ri}>
                {row.map((cell, ci) => (
                  <td key={ci} style={{ padding: '4px 8px', color: 'var(--text-2)',
                                        borderBottom: '1px solid rgba(255,255,255,0.03)',
                                        fontFamily: ci > 0 ? '"JetBrains Mono",monospace' : undefined }}>
                    {fmtVal(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  /* Default: bar */
  const allValues = chart_data.map(d => Number(d[yK]) || 0)
  const maxVal = Math.max(...allValues)
  const isUniform = maxVal === Math.min(...allValues)

  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={chart_data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} barCategoryGap="35%">
        <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
        <XAxis dataKey={xK} {...AXIS_STYLE} />
        <YAxis tickFormatter={fmtVal} width={40} domain={[0, max => Math.ceil(Math.max(max * 1.1, 5))]} {...AXIS_STYLE} />
        <Tooltip content={<Tip />} cursor={{ fill: 'rgba(255,255,255,0.02)' }} />
        <Bar dataKey={yK} radius={[2, 2, 0, 0]} maxBarSize={32} minPointSize={2}>
          {chart_data.map((entry, i) => (
            <Cell key={i}
              fill={Number(entry[yK]) === maxVal && maxVal > 0 && !isUniform ? BRAND : 'rgba(79,107,234,0.38)'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/* ── Chart type icon ────────────────────────────────────── */
function ChartIcon({ type }) {
  const props = { size: 11, strokeWidth: 1.5, style: { color: 'var(--brand)' } }
  if (type === 'line' || type === 'area') return <TrendingUp {...props} />
  if (type === 'pie') return <PieChart {...props} />
  if (type === 'scatter') return <Activity {...props} />
  return <BarChart2 {...props} />
}

/* ── Single Dashboard Panel Card ────────────────────────── */
function DashPanel({ panel }) {
  const [showSql, setShowSql] = useState(false)
  const hasError = Boolean(panel.error)
  const colSpan = Math.min(panel.size?.col_span || 2, 3)

  return (
    <div style={{
      gridColumn: `span ${colSpan}`,
      border: `1px solid ${hasError ? 'rgba(217,64,64,0.25)' : 'var(--border)'}`,
      borderRadius: 6, background: 'var(--surface)',
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden', minHeight: 260,
      boxShadow: '0 2px 12px rgba(0,0,0,0.15)',
      transition: 'box-shadow 0.2s ease',
    }}
    onMouseEnter={e => e.currentTarget.style.boxShadow = '0 4px 24px rgba(79,107,234,0.12)'}
    onMouseLeave={e => e.currentTarget.style.boxShadow = '0 2px 12px rgba(0,0,0,0.15)'}
    >
      {/* Header */}
      <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)',
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          {hasError
            ? <AlertCircle size={11} strokeWidth={1.5} style={{ color: '#E05858' }} />
            : <ChartIcon type={panel.chart_type} />
          }
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)' }}>
            {panel.title}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {panel.row_count != null && !hasError && (
            <span style={{ fontFamily: '"JetBrains Mono",monospace', fontSize: 9,
                           color: 'var(--text-3)' }}>
              {panel.row_count} rows
            </span>
          )}
          {panel.chart_type && !hasError && (
            <span style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.06em',
                           textTransform: 'uppercase', color: 'var(--brand)',
                           padding: '2px 5px', border: '1px solid rgba(79,107,234,0.25)',
                           borderRadius: 2 }}>
              {panel.chart_type}
            </span>
          )}
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, padding: '12px 14px 8px', overflow: 'hidden' }}>
        {hasError ? (
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8,
                        padding: '10px 12px', background: 'rgba(217,64,64,0.06)',
                        border: '1px solid rgba(217,64,64,0.15)', borderRadius: 4 }}>
            <AlertCircle size={13} strokeWidth={1.5} style={{ color: '#E05858', flexShrink: 0, marginTop: 1 }} />
            <p style={{ fontSize: 11, color: '#E05858', lineHeight: 1.6 }}>{panel.error}</p>
          </div>
        ) : (
          <PanelChart panel={panel} />
        )}
      </div>

      {/* Insight summary */}
      {panel.insight_summary && !hasError && (
        <div style={{ padding: '6px 14px 10px', borderTop: '1px solid var(--border)',
                      borderLeft: '2px solid var(--brand)', marginLeft: 14,
                      marginRight: 14, marginBottom: 8 }}>
          <p style={{ fontSize: 11, color: 'var(--text-2)', lineHeight: 1.6, fontStyle: 'italic' }}>
            {panel.insight_summary}
          </p>
        </div>
      )}

      {/* SQL toggle */}
      {panel.sql && (
        <div style={{ borderTop: '1px solid var(--border)', flexShrink: 0 }}>
          <button onClick={() => setShowSql(!showSql)} style={{
            width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '6px 14px', background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-3)', fontSize: 9, fontFamily: '"JetBrains Mono",monospace',
            letterSpacing: '0.06em', textTransform: 'uppercase',
          }}>
            <span>SQL</span>
            {showSql
              ? <ChevronUp size={10} strokeWidth={1.5} />
              : <ChevronDown size={10} strokeWidth={1.5} />
            }
          </button>
          {showSql && (
            <div style={{ padding: '0 14px 10px' }}>
              <pre style={{
                margin: 0, fontSize: 9, color: 'var(--text-2)',
                fontFamily: '"JetBrains Mono",monospace',
                background: 'var(--surface-3)', borderRadius: 3, padding: '8px 10px',
                overflowX: 'auto', lineHeight: 1.7, whiteSpace: 'pre-wrap',
                maxHeight: 120, overflowY: 'auto',
              }}>{panel.sql}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* ── Skeleton loader ────────────────────────────────────── */
function Skeleton({ cols }) {
  return Array.from({ length: cols || 4 }).map((_, i) => (
    <div key={i} style={{
      gridColumn: i % 3 === 0 ? 'span 3' : 'span 3',
      height: 280, borderRadius: 6,
      background: 'linear-gradient(90deg, var(--surface) 25%, var(--surface-3) 50%, var(--surface) 75%)',
      backgroundSize: '200% 100%',
      animation: 'shimmer 1.5s infinite',
      border: '1px solid var(--border)',
    }} />
  ))
}

/* ── Main Dashboard Page ────────────────────────────────── */
export default function Dashboard() {
  const [request, setRequest] = useState('')
  const [dashboard, setDashboard] = useState(null)
  const inputRef = useRef(null)

  const { mutate, isPending } = useMutation({
    mutationFn: (req) => dashboardApi.generate(req).then(r => r.data),
    onSuccess: (data) => {
      setDashboard(data)
      toast.success(`Dashboard ready — ${data.panels.length} panels generated`)
    },
    onError: (err) => {
      toast.error(err.response?.data?.message || 'Dashboard generation failed')
    },
  })

  const handleGenerate = (q) => {
    const query = q || request.trim()
    if (!query) return
    setRequest(query)
    setDashboard(null)
    mutate(query)
  }

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '28px 36px' }}>

      {/* ── Page heading ─────────────────────────────────── */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 4,
            background: 'linear-gradient(135deg,rgba(79,107,234,0.25),rgba(79,107,234,0.08))',
            border: '1px solid rgba(79,107,234,0.20)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <LayoutDashboard size={16} strokeWidth={1.5} style={{ color: 'var(--brand)' }} />
          </div>
          <h1 className="heading-lg">Auto Dashboard</h1>
          <span style={{
            fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
            color: '#0EA861', padding: '3px 7px', border: '1px solid rgba(14,168,97,0.3)',
            borderRadius: 3, marginLeft: 4,
          }}>AI-powered</span>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6 }}>
          Describe what you want to analyse. The engine decomposes your request into
          multiple SQL queries, selects optimal charts, and assembles a live dashboard.
        </p>
      </div>

      {/* ── Generator input ──────────────────────────────── */}
      <div style={{
        border: '1px solid rgba(79,107,234,0.25)', borderRadius: 6,
        background: 'var(--surface)', marginBottom: 24,
        boxShadow: '0 0 0 4px rgba(79,107,234,0.04)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px' }}>
          <Sparkles size={14} strokeWidth={1.5} style={{ color: 'var(--brand)', flexShrink: 0 }} />
          <input
            ref={inputRef}
            value={request}
            onChange={e => setRequest(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleGenerate()}
            placeholder='Describe your dashboard — e.g. "Show hospital admissions trends"'
            disabled={isPending}
            style={{
              flex: 1, background: 'none', border: 'none', outline: 'none',
              fontSize: 13.5, color: 'var(--text-1)',
              fontFamily: "'Plus Jakarta Sans', sans-serif",
            }}
          />
          <button
            onClick={() => handleGenerate()}
            disabled={isPending || !request.trim()}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '7px 14px', borderRadius: 4, border: 'none',
              background: isPending || !request.trim() ? 'var(--surface-3)' : 'var(--brand)',
              color: isPending || !request.trim() ? 'var(--text-3)' : '#fff',
              cursor: isPending || !request.trim() ? 'not-allowed' : 'pointer',
              fontSize: 12, fontWeight: 600, transition: 'all 0.15s ease', flexShrink: 0,
            }}
          >
            <Send size={11} strokeWidth={2} />
            {isPending ? 'Generating…' : 'Generate'}
          </button>
        </div>

        {/* Suggestions */}
        {!isPending && !dashboard && (
          <div style={{
            padding: '10px 14px 12px', borderTop: '1px solid var(--border)',
            display: 'flex', flexWrap: 'wrap', gap: 6,
          }}>
            {SUGGESTIONS.map(s => (
              <button key={s} onClick={() => handleGenerate(s)} style={{
                padding: '4px 10px', borderRadius: 30, fontSize: 11,
                background: 'rgba(79,107,234,0.07)',
                border: '1px solid rgba(79,107,234,0.18)',
                color: 'var(--brand)', cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'rgba(79,107,234,0.15)'}
              onMouseLeave={e => e.currentTarget.style.background = 'rgba(79,107,234,0.07)'}
              >{s}</button>
            ))}
          </div>
        )}
      </div>

      {/* ── Loading skeleton ─────────────────────────────── */}
      {isPending && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <div style={{
              width: 8, height: 8, borderRadius: '50%', background: 'var(--brand)',
              animation: 'pulse 1s ease-in-out infinite',
            }} />
            <span style={{ fontSize: 12, color: 'var(--text-2)' }}>
              Planning queries → Executing SQL → Selecting charts → Composing summary…
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 16 }}>
            <Skeleton cols={4} />
          </div>
          <style>{`
            @keyframes shimmer {
              0%  { background-position: -200% 0; }
              100%{ background-position:  200% 0; }
            }
            @keyframes pulse {
              0%,100%{ opacity:1; transform:scale(1); }
              50%     { opacity:0.5; transform:scale(0.8); }
            }
          `}</style>
        </>
      )}

      {/* ── Dashboard result ─────────────────────────────── */}
      {dashboard && !isPending && (
        <>
          {/* Dashboard header */}
          <div style={{
            display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
            marginBottom: 20, gap: 20,
          }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-1)', margin: 0 }}>
                  {dashboard.title}
                </h2>
                <span style={{
                  fontSize: 9, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
                  padding: '3px 7px', border: '1px solid rgba(14,168,97,0.3)',
                  borderRadius: 3, color: '#0EA861',
                }}>
                  {dashboard.layout.success_count}/{dashboard.layout.panel_count} panels
                </span>
                <span style={{
                  fontFamily: '"JetBrains Mono",monospace', fontSize: 9, color: 'var(--text-3)',
                }}>
                  {dashboard.total_rows?.toLocaleString()} total rows
                </span>
              </div>

              {/* Executive summary */}
              {dashboard.summary && (
                <div style={{
                  padding: '10px 14px', borderRadius: 4,
                  background: 'rgba(79,107,234,0.06)',
                  border: '1px solid rgba(79,107,234,0.15)',
                  borderLeft: '3px solid var(--brand)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6 }}>
                    <Sparkles size={11} strokeWidth={1.5} style={{ color: 'var(--brand)' }} />
                    <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
                                   textTransform: 'uppercase', color: 'var(--brand)' }}>
                      Executive Summary
                    </span>
                  </div>
                  <p style={{ fontSize: 12.5, color: 'var(--text-1)', lineHeight: 1.7, margin: 0 }}>
                    {dashboard.summary}
                  </p>
                </div>
              )}
            </div>

            {/* Stat badges */}
            <div style={{ display: 'flex', gap: 8, flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              {[
                { icon: Layers,    label: 'Panels',    val: dashboard.panels.length },
                { icon: Database,  label: 'Rows',      val: dashboard.total_rows?.toLocaleString() },
              ].map(({ icon: Icon, label, val }) => (
                <div key={label} style={{
                  padding: '8px 14px', borderRadius: 4, border: '1px solid var(--border)',
                  background: 'var(--surface)', textAlign: 'center', minWidth: 70,
                }}>
                  <Icon size={12} strokeWidth={1.5} style={{ color: 'var(--brand)', marginBottom: 4 }} />
                  <p style={{ fontFamily: '"JetBrains Mono",monospace', fontSize: 16,
                               fontWeight: 600, color: 'var(--text-1)', margin: 0 }}>{val}</p>
                  <p style={{ fontSize: 9, color: 'var(--text-3)', marginTop: 2,
                               textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Panel grid */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(6, 1fr)',
            gap: 16,
            alignItems: 'start',
          }}>
            {dashboard.panels.map(panel => (
              <DashPanel key={panel.id} panel={panel} />
            ))}
          </div>

          {/* Re-generate button */}
          <div style={{ marginTop: 28, display: 'flex', justifyContent: 'center' }}>
            <button
              onClick={() => { setDashboard(null); inputRef.current?.focus() }}
              style={{
                padding: '8px 20px', borderRadius: 4,
                border: '1px solid var(--border)', background: 'var(--surface)',
                color: 'var(--text-2)', cursor: 'pointer', fontSize: 12,
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--brand)'; e.currentTarget.style.color = 'var(--brand)' }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-2)' }}
            >
              Generate a new dashboard
            </button>
          </div>
        </>
      )}
    </div>
  )
}
