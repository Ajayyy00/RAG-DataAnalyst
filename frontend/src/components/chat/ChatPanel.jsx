import { useEffect, useRef } from 'react'
import { useChatStore } from '../../store/chatStore'
import ChatMessage from './ChatMessage'
import ChatInput from './ChatInput'
import { Activity } from 'lucide-react'

const EXAMPLES = [
  { label: 'Diagnoses',    query: 'Top 10 diagnoses by frequency this quarter' },
  { label: 'Readmissions', query: 'Monthly 30-day readmission trends, last 6 months' },
  { label: 'Length of stay', query: 'Average LOS by department, last 90 days' },
  { label: 'Medications',  query: 'Most prescribed medications this month' },
]

function Typing({ step }) {
  return (
    <div className="msg-ai anim-in">
      <div className="msg-ai-avatar">
        <Activity size={12} strokeWidth={1.5} style={{ color: 'var(--brand)' }} />
      </div>
      <div style={{
        border: '1px solid var(--border)', borderRadius: 4,
        padding: '10px 14px', background: 'var(--surface)',
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <div style={{ display: 'flex', gap: 4 }}>
          <span className="dot" />
          <span className="dot" />
          <span className="dot" />
        </div>
        {step && (
          <span style={{
            fontSize: 11, fontFamily: "'Plus Jakarta Sans', sans-serif",
            fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase',
            color: 'var(--brand)',
          }}>
            {step}
          </span>
        )}
      </div>
    </div>
  )
}

function EmptyState({ onSend }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <Activity size={20} strokeWidth={1.5} />
      </div>

      <h2 className="heading-lg" style={{ marginBottom: 8 }}>Healthcare Data Analyst</h2>
      <p style={{ fontSize: 13, color: 'var(--text-2)', maxWidth: 380, lineHeight: 1.65, marginBottom: 36 }}>
        Ask anything in plain English. The system generates SQL, executes it
        against your data warehouse, and returns tables, charts, and clinical insights.
      </p>

      <div style={{ width: '100%', maxWidth: 540 }}>
        <p className="overline" style={{ marginBottom: 12, textAlign: 'left' }}>Try an example</p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          {EXAMPLES.map(({ label, query }) => (
            <button key={label} className="example-card" onClick={() => onSend?.(query)}>
              <p className="example-label">{label}</p>
              <p style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.55 }}>{query}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function ChatPanel({ onSend }) {
  const messages      = useChatStore((s) => s.messages)
  const isStreaming   = useChatStore((s) => s.isStreaming)
  const streamingStep = useChatStore((s) => s.streamingStep)
  const bottomRef     = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="chat-scroll">
        {messages.length === 0 ? (
          <EmptyState onSend={onSend} />
        ) : (
          <div className="chat-width">
            {messages.map((msg) => <ChatMessage key={msg.id} message={msg} />)}
            {isStreaming && <Typing step={streamingStep} />}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
      <ChatInput onSend={onSend} disabled={isStreaming} />
    </div>
  )
}
