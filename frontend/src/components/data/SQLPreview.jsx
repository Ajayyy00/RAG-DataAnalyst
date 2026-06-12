import { useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { Copy, Check, ChevronDown, ChevronUp } from 'lucide-react'

// Bespoke minimalist SQL theme — monochrome base, accent on keywords only
const SQL_THEME = {
  'code[class*="language-"]': {
    color: '#6E7D96',
    background: 'none',
    fontFamily: '"JetBrains Mono", monospace',
    fontSize: '12px',
    lineHeight: '1.75',
    textAlign: 'left',
    whiteSpace: 'pre',
    wordSpacing: 'normal',
    wordBreak: 'normal',
  },
  'pre[class*="language-"]': {
    background: 'var(--canvas)',
    padding: '14px 18px',
    margin: 0,
    overflow: 'auto',
  },
  keyword:     { color: '#7AA2F7', fontWeight: '500' },
  builtin:     { color: '#7DCFFF' },
  function:    { color: '#7DCFFF' },
  string:      { color: '#9ECE6A' },
  number:      { color: '#E0AF68' },
  comment:     { color: '#38455A', fontStyle: 'italic' },
  operator:    { color: '#89DDFF' },
  punctuation: { color: '#4A5568' },
  'class-name':{ color: '#DCE0EC' },
  boolean:     { color: '#E0AF68' },
}

export default function SQLPreview({ sql, isValid }) {
  const [copied, setCopied]     = useState(false)
  const [expanded, setExpanded] = useState(false)
  if (!sql) return null

  const copy = () => {
    navigator.clipboard.writeText(sql)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  const lineCount = sql.trim().split('\n').length

  return (
    <div className="data-panel">
      {/* Header */}
      <div className="data-panel-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="overline">SQL</span>
          <span className="caption" style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 10 }}>
            {lineCount} line{lineCount !== 1 ? 's' : ''}
          </span>
          {isValid !== undefined && (
            isValid
              ? <span className="badge-valid">✓ Valid</span>
              : <span className="badge-invalid">✕ Invalid</span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <button onClick={copy} className="btn-ghost" style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '4px 8px', fontSize: 11 }}>
            {copied
              ? <><Check size={11} strokeWidth={1.5} style={{ color: 'var(--green)' }} /><span style={{ color: 'var(--green)' }}>Copied</span></>
              : <><Copy size={11} strokeWidth={1.5} />Copy</>
            }
          </button>
          <button onClick={() => setExpanded(!expanded)} className="btn-ghost">
            {expanded
              ? <ChevronUp size={13} strokeWidth={1.5} />
              : <ChevronDown size={13} strokeWidth={1.5} />
            }
          </button>
        </div>
      </div>

      {/* Code */}
      <div style={{ maxHeight: expanded ? 360 : 120, overflow: 'auto', transition: 'max-height 150ms ease-in-out' }}>
        <SyntaxHighlighter language="sql" style={SQL_THEME} wrapLongLines>
          {sql}
        </SyntaxHighlighter>
      </div>

      {/* Expand toggle */}
      {!expanded && lineCount > 4 && (
        <button
          onClick={() => setExpanded(true)}
          style={{
            width: '100%', padding: '6px', fontSize: 11,
            background: 'transparent', border: 'none',
            borderTop: '1px solid var(--border)',
            color: 'var(--text-3)', cursor: 'pointer',
            transition: 'color 150ms ease-in-out, background 150ms ease-in-out',
            fontFamily: "'Plus Jakarta Sans', sans-serif", fontWeight: 600, letterSpacing: '0.04em',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--brand)'; e.currentTarget.style.background = 'var(--brand-dim)' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-3)'; e.currentTarget.style.background = 'transparent' }}
        >
          SHOW FULL QUERY ↓
        </button>
      )}
    </div>
  )
}
