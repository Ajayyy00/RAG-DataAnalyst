import SQLPreview from '../data/SQLPreview'
import ResultTable from '../data/ResultTable'
import ChartPanel from '../viz/ChartPanel'
import InsightsPanel from './InsightsPanel'
import { Activity, AlertTriangle } from 'lucide-react'

function UserMessage({ content, timestamp }) {
  return (
    <div className="msg-user anim-in">
      <div>
        <div className="msg-user-bubble">{content}</div>
        <p className="caption" style={{ marginTop: 5, textAlign: 'right' }}>
          {new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
    </div>
  )
}

function AssistantMessage({ msg }) {
  return (
    <div className="msg-ai anim-in">
      {/* Avatar */}
      <div className="msg-ai-avatar">
        <Activity size={12} strokeWidth={1.5} style={{ color: 'var(--brand)' }} />
      </div>

      {/* Content */}
      <div className="msg-ai-body">
        {msg.error ? (
          <div style={{
            display: 'flex', alignItems: 'flex-start', gap: 10,
            border: '1px solid rgba(217,64,64,0.18)', borderRadius: 4,
            padding: '10px 14px', background: 'rgba(217,64,64,0.05)',
          }}>
            <AlertTriangle size={14} strokeWidth={1.5} style={{ color: 'var(--red)', flexShrink: 0, marginTop: 1 }} />
            <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6 }}>{msg.error}</p>
          </div>
        ) : (
          <>
            {msg.sql     && <SQLPreview sql={msg.sql} isValid={msg.isValid} />}
            {msg.columns?.length > 0 && <ResultTable columns={msg.columns} rows={msg.rows} rowCount={msg.rowCount} />}
            {msg.chartType && <ChartPanel chartType={msg.chartType} chartConfig={msg.chartConfig} />}
            {(msg.insightReport || msg.insights?.length > 0) && (
              <InsightsPanel
                insights={msg.insights || []}
                insightReport={msg.insightReport}
              />
            )}
          </>
        )}
        <p className="caption" style={{ marginTop: 4 }}>
          {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
    </div>
  )
}

export default function ChatMessage({ message }) {
  if (message.role === 'user') return <UserMessage content={message.content} timestamp={message.timestamp} />
  return <AssistantMessage msg={message} />
}
