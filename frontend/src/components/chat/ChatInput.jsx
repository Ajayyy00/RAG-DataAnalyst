import { useState, useRef } from 'react'
import { Send, CornerDownLeft } from 'lucide-react'

const PILLS = [
  'Top diagnoses this quarter',
  'Average LOS by department',
  'Readmission trends last 6 months',
  'Medication adherence rate',
]

export default function ChatInput({ onSend, disabled }) {
  const [value, setValue] = useState('')
  const ref = useRef(null)

  const submit = () => {
    const q = value.trim()
    if (!q || disabled) return
    onSend(q)
    setValue('')
    if (ref.current) { ref.current.style.height = 'auto' }
  }

  const onKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }
  }

  const onInput = (e) => {
    setValue(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px'
  }

  return (
    <div className="chat-input-bar">
      <div className="chat-input-box">

        {/* Pills */}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
          {PILLS.map((p) => (
            <button key={p} className="pill" onClick={() => { setValue(p); ref.current?.focus() }}>
              {p}
            </button>
          ))}
        </div>

        {/* Input row */}
        <div className="chat-input-field">
          <textarea
            ref={ref}
            rows={1}
            value={value}
            onChange={onInput}
            onKeyDown={onKey}
            disabled={disabled}
            className="chat-textarea"
            placeholder="Ask a clinical data question… (Enter to send, Shift+Enter for new line)"
            id="chat-input"
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
            <span className="caption" style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <CornerDownLeft size={10} strokeWidth={1.5} /> Send
            </span>
            <button
              onClick={submit}
              disabled={!value.trim() || disabled}
              className="btn btn-primary"
              style={{ padding: '6px 12px', fontSize: 12 }}
              id="send-btn"
            >
              <Send size={12} strokeWidth={1.5} />
            </button>
          </div>
        </div>

        <p className="caption" style={{ marginTop: 8, textAlign: 'center' }}>
          SQL is validated and read-only before execution · Results are never cached to disk
        </p>
      </div>
    </div>
  )
}
