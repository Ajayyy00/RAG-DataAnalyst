import { useState } from 'react'
import {
  ChevronDown, ChevronUp, TrendingUp, AlertTriangle,
  Lightbulb, HelpCircle, Database, Activity,
} from 'lucide-react'

// ── Priority badge colours ────────────────────────────────────
const PRIORITY_COLOR = {
  high:   { bg: 'rgba(217,64,64,0.12)',   text: '#E05858', border: 'rgba(217,64,64,0.25)' },
  medium: { bg: 'rgba(245,158,11,0.12)',  text: '#F59E0B', border: 'rgba(245,158,11,0.25)' },
  low:    { bg: 'rgba(14,168,97,0.12)',   text: '#0EA861', border: 'rgba(14,168,97,0.25)' },
}

const CONFIDENCE_COLOR = {
  high:   '#0EA861',
  medium: '#F59E0B',
  low:    '#E05858',
}

// ── Section header ────────────────────────────────────────────
function SectionHeader({ icon: Icon, label, count, color = 'var(--text-2)' }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, marginTop: 14 }}>
      <Icon size={11} strokeWidth={1.8} style={{ color }} />
      <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
                     textTransform: 'uppercase', color }}>
        {label}
      </span>
      {count > 0 && (
        <span style={{ fontSize: 9, fontFamily: '"JetBrains Mono", monospace',
                       color: 'var(--text-3)', marginLeft: 2 }}>
          ({count})
        </span>
      )}
    </div>
  )
}

// ── Bullet item ────────────────────────────────────────────────
function BulletItem({ text, index, accentColor = 'var(--brand)' }) {
  return (
    <div className="anim-in" style={{ display: 'flex', gap: 10, marginBottom: 7,
                                       animationDelay: `${index * 35}ms` }}>
      <span style={{
        fontFamily: '"JetBrains Mono", monospace', fontSize: 9, fontWeight: 600,
        color: accentColor, flexShrink: 0, paddingTop: 2, minWidth: 18,
      }}>
        {String(index + 1).padStart(2, '0')}
      </span>
      <p style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, margin: 0 }}>{text}</p>
    </div>
  )
}

// ── Recommendation card ────────────────────────────────────────
function RecommendationCard({ rec, index }) {
  const colors = PRIORITY_COLOR[rec.priority] || PRIORITY_COLOR.medium
  return (
    <div className="anim-in" style={{
      border: `1px solid ${colors.border}`,
      borderRadius: 4,
      padding: '9px 12px',
      marginBottom: 7,
      background: colors.bg,
      animationDelay: `${index * 40}ms`,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
        <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)', margin: 0, lineHeight: 1.4 }}>
          {rec.action}
        </p>
        <span style={{
          fontSize: 8, fontWeight: 700, letterSpacing: '0.08em',
          textTransform: 'uppercase', color: colors.text,
          padding: '2px 5px', border: `1px solid ${colors.border}`,
          borderRadius: 2, flexShrink: 0,
        }}>
          {rec.priority}
        </span>
      </div>
      {rec.rationale && (
        <p style={{ fontSize: 11, color: 'var(--text-2)', margin: '5px 0 0', lineHeight: 1.5 }}>
          {rec.rationale}
        </p>
      )}
      {rec.metric && (
        <p style={{ fontSize: 10, fontFamily: '"JetBrains Mono", monospace',
                    color: 'var(--text-3)', margin: '4px 0 0' }}>
          Metric: {rec.metric}
        </p>
      )}
    </div>
  )
}

// ── Follow-up question chips ────────────────────────────────────
function FollowUpChip({ question, onClick }) {
  const [hover, setHover] = useState(false)
  return (
    <button
      onClick={() => onClick?.(question)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background: hover ? 'rgba(79,107,234,0.12)' : 'rgba(79,107,234,0.06)',
        border: '1px solid rgba(79,107,234,0.20)',
        borderRadius: 3, padding: '5px 10px', cursor: 'pointer',
        fontSize: 11, color: 'var(--brand)', textAlign: 'left',
        transition: 'all 0.15s ease', lineHeight: 1.4,
      }}
    >
      {question}
    </button>
  )
}

// ── Main component ────────────────────────────────────────────
export default function InsightsPanel({ insights = [], insightReport, onFollowUp }) {
  const [collapsed, setCollapsed] = useState(false)

  // Support both rich insightReport object and legacy flat insights array
  const report = insightReport
  const hasReport = report && (
    report.summary || report.trends?.length || report.recommendations?.length
  )

  // Legacy fallback
  if (!hasReport && !insights.length) return null

  const totalItems = hasReport
    ? (report.trends?.length || 0) + (report.anomalies?.length || 0) +
      (report.recommendations?.length || 0)
    : insights.length

  return (
    <div className="data-panel">
      {/* Header */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="data-panel-header"
        style={{ width: '100%', background: 'none', border: 'none',
                 cursor: 'pointer', textAlign: 'left' }}
      >
        <span className="overline" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Activity size={11} strokeWidth={1.5} style={{ color: 'var(--brand)' }} />
          AI Insights
          <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 9,
                         fontWeight: 500, color: 'var(--brand)', letterSpacing: '0.04em' }}>
            {totalItems}
          </span>
          {hasReport && report.confidence && (
            <span style={{
              fontSize: 8, fontWeight: 700, letterSpacing: '0.06em',
              textTransform: 'uppercase', padding: '2px 5px',
              border: `1px solid ${CONFIDENCE_COLOR[report.confidence]}40`,
              borderRadius: 2, color: CONFIDENCE_COLOR[report.confidence],
            }}>
              {report.confidence} confidence
            </span>
          )}
        </span>
        {collapsed
          ? <ChevronDown size={12} strokeWidth={1.5} style={{ color: 'var(--text-3)' }} />
          : <ChevronUp   size={12} strokeWidth={1.5} style={{ color: 'var(--text-3)' }} />
        }
      </button>

      {!collapsed && (
        <div style={{ padding: '4px 16px 14px' }}>

          {hasReport ? (
            <>
              {/* Summary */}
              {report.summary && (
                <p style={{
                  fontSize: 12.5, color: 'var(--text-1)', lineHeight: 1.65,
                  margin: '8px 0 4px', fontStyle: 'italic',
                  borderLeft: '2px solid var(--brand)',
                  paddingLeft: 10,
                }}>
                  {report.summary}
                </p>
              )}

              {/* Trends */}
              {report.trends?.length > 0 && (
                <>
                  <SectionHeader icon={TrendingUp} label="Key Trends"
                                 count={report.trends.length} color="#4F6BEA" />
                  {report.trends.map((t, i) =>
                    <BulletItem key={i} text={t} index={i} accentColor="#4F6BEA" />
                  )}
                </>
              )}

              {/* Anomalies */}
              {report.anomalies?.length > 0 && (
                <>
                  <SectionHeader icon={AlertTriangle} label="Anomalies"
                                 count={report.anomalies.length} color="#E05858" />
                  {report.anomalies.map((a, i) =>
                    <BulletItem key={i} text={a} index={i} accentColor="#E05858" />
                  )}
                </>
              )}

              {/* Recommendations */}
              {report.recommendations?.length > 0 && (
                <>
                  <SectionHeader icon={Lightbulb} label="Recommendations"
                                 count={report.recommendations.length} color="#F59E0B" />
                  {report.recommendations.map((r, i) =>
                    <RecommendationCard key={i} rec={r} index={i} />
                  )}
                </>
              )}

              {/* Data Quality */}
              {report.data_quality_notes?.length > 0 && (
                <>
                  <SectionHeader icon={Database} label="Data Quality"
                                 count={report.data_quality_notes.length} color="var(--text-3)" />
                  {report.data_quality_notes.map((n, i) =>
                    <BulletItem key={i} text={n} index={i} accentColor="var(--text-3)" />
                  )}
                </>
              )}

              {/* Follow-up questions */}
              {report.follow_up_questions?.length > 0 && (
                <>
                  <SectionHeader icon={HelpCircle} label="Suggested Follow-ups"
                                 count={report.follow_up_questions.length} color="var(--brand)" />
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 2 }}>
                    {report.follow_up_questions.map((q, i) => (
                      <FollowUpChip key={i} question={q} onClick={onFollowUp} />
                    ))}
                  </div>
                </>
              )}
            </>
          ) : (
            /* Legacy flat list fallback */
            insights.map((text, i) => (
              <div key={i} className="insight-item anim-in"
                   style={{ animationDelay: `${i * 40}ms` }}>
                <span className="insight-num">{String(i + 1).padStart(2, '0')}</span>
                <p className="insight-text">{text}</p>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
