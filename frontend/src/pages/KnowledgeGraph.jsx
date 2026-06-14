import { useState, useCallback, useRef } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import ForceGraph2D from 'react-force-graph-2d'
import {
  Share2, Search, RefreshCw, Zap, Database, Activity,
  GitBranch, Pill, FlaskConical, ChevronRight, Loader2, AlertCircle,
} from 'lucide-react'
import { kgApi } from '../api/kg'
import toast from 'react-hot-toast'

/* ── Node colour palette ──────────────────────────────────── */
const NODE_COLORS = {
  Patient:    '#4F6BEA',   // brand indigo
  Disease:    '#D94040',   // red
  Symptom:    '#C47D0A',   // amber
  Medication: '#0EA861',   // green
  LabTest:    '#8B5CF6',   // purple
}

const NODE_ICONS = {
  Patient:    '👤',
  Disease:    '🦠',
  Symptom:    '⚡',
  Medication: '💊',
  LabTest:    '🧪',
}

const ENTITY_ICONS = {
  Patient:    Activity,
  Disease:    AlertCircle,
  Symptom:    Zap,
  Medication: Pill,
  LabTest:    FlaskConical,
}

/* ── Demo / placeholder graph when backend is offline ─────── */
const DEMO_GRAPH = {
  nodes: [
    { id: 'p1', label: 'Alice Johnson', type: 'Patient' },
    { id: 'p2', label: 'Bob Smith', type: 'Patient' },
    { id: 'd1', label: 'Type 2 Diabetes', type: 'Disease' },
    { id: 'd2', label: 'Hypertension', type: 'Disease' },
    { id: 's1', label: 'Fatigue', type: 'Symptom' },
    { id: 's2', label: 'Polyuria', type: 'Symptom' },
    { id: 's3', label: 'Headache', type: 'Symptom' },
    { id: 'm1', label: 'Metformin', type: 'Medication' },
    { id: 'm2', label: 'Lisinopril', type: 'Medication' },
    { id: 'l1', label: 'HbA1c', type: 'LabTest' },
    { id: 'l2', label: 'BMP Panel', type: 'LabTest' },
  ],
  links: [
    { source: 'p1', target: 'd1', label: 'HAS_DISEASE' },
    { source: 'p2', target: 'd2', label: 'HAS_DISEASE' },
    { source: 'p1', target: 'm1', label: 'PRESCRIBED' },
    { source: 'p2', target: 'm2', label: 'PRESCRIBED' },
    { source: 'd1', target: 's1', label: 'HAS_SYMPTOM' },
    { source: 'd1', target: 's2', label: 'HAS_SYMPTOM' },
    { source: 'd2', target: 's3', label: 'HAS_SYMPTOM' },
    { source: 'p1', target: 's1', label: 'EXHIBITS' },
    { source: 'p1', target: 'l1', label: 'TOOK_TEST' },
    { source: 'p2', target: 'l2', label: 'TOOK_TEST' },
    { source: 'm1', target: 'd1', label: 'TREATS' },
    { source: 'm2', target: 'd2', label: 'TREATS' },
  ],
}

/* ── Convert graph_data rows → force-graph schema ─────────── */
function parseGraphData(rows) {
  if (!rows?.length) return DEMO_GRAPH
  const nodeMap = {}
  const links = []
  rows.forEach((row) => {
    Object.values(row).forEach((val) => {
      if (val && typeof val === 'object') {
        if (val.id && val.labels) {
          const id = String(val.id)
          if (!nodeMap[id]) {
            nodeMap[id] = {
              id,
              label: val.properties?.name || val.properties?.first_name || id,
              type: val.labels[0] || 'Node',
            }
          }
        } else if (val.type && val.start_node_id != null) {
          links.push({
            source: String(val.start_node_id),
            target: String(val.end_node_id),
            label: val.type,
          })
        }
      }
    })
  })
  return { nodes: Object.values(nodeMap), links }
}

/* ── Stats chip ───────────────────────────────────────────── */
function StatChip({ label, value, icon: Icon, color }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '10px 14px', borderRadius: 10,
      background: 'var(--surface-2)', border: '1px solid var(--border)',
    }}>
      <div style={{
        width: 32, height: 32, borderRadius: 8,
        background: color + '18', display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Icon size={15} color={color} />
      </div>
      <div>
        <p style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-1)', lineHeight: 1 }}>{value ?? '—'}</p>
        <p className="caption" style={{ marginTop: 2 }}>{label}</p>
      </div>
    </div>
  )
}

/* ── Node legend pill ─────────────────────────────────────── */
function LegendPill({ type }) {
  const Icon = ENTITY_ICONS[type] || Database
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 5,
      padding: '4px 9px', borderRadius: 20,
      background: NODE_COLORS[type] + '18',
      border: `1px solid ${NODE_COLORS[type]}40`,
    }}>
      <Icon size={10} color={NODE_COLORS[type]} />
      <span style={{ fontSize: 10, fontWeight: 600, color: NODE_COLORS[type] }}>{type}</span>
    </div>
  )
}

/* ── Main page ────────────────────────────────────────────── */
export default function KnowledgeGraph() {
  const graphRef = useRef()
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(null)
  const [graphData, setGraphData] = useState(DEMO_GRAPH)
  const [hoveredNode, setHoveredNode] = useState(null)
  const [selectedNode, setSelectedNode] = useState(null)

  /* Stats */
  const { data: statsData } = useQuery({
    queryKey: ['kg-stats'],
    queryFn: () => kgApi.stats().then((r) => r.data),
    retry: 1,
    staleTime: 60_000,
  })

  /* Sync */
  const syncMutation = useMutation({
    mutationFn: () => kgApi.sync(),
    onSuccess: () => toast.success('Knowledge Graph sync started in background'),
    onError: () => toast.error('Sync failed — is Neo4j running?'),
  })

  /* Query */
  const queryMutation = useMutation({
    mutationFn: (q) => kgApi.query(q).then((r) => r.data),
    onSuccess: (data) => {
      setAnswer(data)
      if (data.graph_data?.length) {
        setGraphData(parseGraphData(data.graph_data))
      }
    },
    onError: () => toast.error('Query failed'),
  })

  const handleQuery = useCallback((e) => {
    e.preventDefault()
    if (!question.trim()) return
    queryMutation.mutate(question)
  }, [question, queryMutation])

  /* Sample queries */
  const SAMPLES = [
    'Which patients have Type 2 Diabetes?',
    'What medications treat Hypertension?',
    'Show symptoms associated with Heart Disease',
    'Which patients took lab test HbA1c?',
  ]

  /* Force graph render node */
  const paintNode = useCallback((node, ctx, globalScale) => {
    const color = NODE_COLORS[node.type] || '#4F6BEA'
    const r = 7
    const isHovered = hoveredNode?.id === node.id
    const isSelected = selectedNode?.id === node.id

    // Glow
    if (isHovered || isSelected) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, r + 5, 0, Math.PI * 2)
      ctx.fillStyle = color + '30'
      ctx.fill()
    }

    // Circle
    ctx.beginPath()
    ctx.arc(node.x, node.y, r, 0, Math.PI * 2)
    ctx.fillStyle = isSelected ? color : color + 'CC'
    ctx.fill()

    // Border
    ctx.strokeStyle = isHovered ? '#fff' : color + '80'
    ctx.lineWidth = isHovered ? 1.5 : 0.8
    ctx.stroke()

    // Label at sufficient zoom
    if (globalScale >= 1.0 || isHovered) {
      const fontSize = isHovered ? 6 : Math.min(6 / globalScale + 2, 5)
      ctx.font = `${fontSize}px Inter`
      ctx.fillStyle = isHovered ? '#FFFFFF' : '#DCE0ED'
      ctx.textAlign = 'center'
      ctx.fillText(
        node.label?.length > 20 ? node.label.slice(0, 19) + '…' : (node.label || node.id),
        node.x, node.y + r + (fontSize / 2) + 2
      )
    }
  }, [hoveredNode, selectedNode])

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: 'var(--canvas)', overflow: 'hidden' }}>

      {/* ── Header ───────────────────────────────────────── */}
      <div style={{
        padding: '16px 24px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 14, flexShrink: 0,
        background: 'var(--surface)',
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: 10,
          background: 'var(--brand-dim)', border: '1px solid var(--brand-border)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Share2 size={17} color="var(--brand)" />
        </div>
        <div>
          <h1 className="heading-sm" style={{ fontSize: 15 }}>Knowledge Graph</h1>
          <p className="caption">Healthcare entity relationships powered by Neo4j + LLM reasoning</p>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '7px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600,
              background: 'var(--surface-2)', border: '1px solid var(--border)',
              color: 'var(--text-1)', cursor: 'pointer', transition: 'all 0.15s',
            }}
          >
            <RefreshCw size={13} style={{ animation: syncMutation.isPending ? 'spin 1s linear infinite' : 'none' }} />
            {syncMutation.isPending ? 'Syncing…' : 'Sync Graph'}
          </button>
        </div>
      </div>

      {/* ── Body ─────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>

        {/* ── Left panel: Graph ───────────────────────── */}
        <div style={{ flex: 1, position: 'relative', overflow: 'hidden', minWidth: 0 }}>

          {/* Offline Banner */}
          {statsData?.neo4j_available === false && (
            <div style={{
              position: 'absolute', top: 0, left: 0, right: 0, zIndex: 20,
              background: 'var(--amber)', color: '#fff', padding: '8px 14px',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              fontSize: 12, fontWeight: 600,
            }}>
              <AlertCircle size={14} />
              Neo4j is currently offline. Showing sample demo graph.
            </div>
          )}

          {/* Legend */}
          <div style={{
            position: 'absolute', top: statsData?.neo4j_available === false ? 44 : 14, left: 14, zIndex: 10,
            display: 'flex', gap: 6, flexWrap: 'wrap',
          }}>
            {Object.keys(NODE_COLORS).map((t) => <LegendPill key={t} type={t} />)}
          </div>

          {/* Node count badge */}
          <div style={{
            position: 'absolute', bottom: 14, left: 14, zIndex: 10,
            padding: '4px 10px', borderRadius: 8,
            background: 'var(--surface)', border: '1px solid var(--border)',
            fontSize: 11, color: 'var(--text-2)',
          }}>
            {graphData.nodes.length} nodes · {graphData.links.length} edges
          </div>

          {/* Hovered node tooltip */}
          {hoveredNode && (
            <div style={{
              position: 'absolute', bottom: 14, left: '50%', transform: 'translateX(-50%)',
              zIndex: 10, padding: '8px 14px', borderRadius: 10,
              background: 'var(--surface-3)', border: `1px solid ${NODE_COLORS[hoveredNode.type]}40`,
              display: 'flex', alignItems: 'center', gap: 8, pointerEvents: 'none',
            }}>
              <span style={{ fontSize: 14 }}>{NODE_ICONS[hoveredNode.type]}</span>
              <div>
                <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)' }}>{hoveredNode.label || hoveredNode.id}</p>
                <p style={{ fontSize: 10, color: NODE_COLORS[hoveredNode.type] }}>{hoveredNode.type}</p>
              </div>
            </div>
          )}

          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            backgroundColor="#0B0D14"
            nodeCanvasObject={paintNode}
            nodeCanvasObjectMode={() => 'replace'}
            linkColor={() => 'rgba(255, 255, 255, 0.25)'}
            linkWidth={1.5}
            linkDirectionalArrowLength={5}
            linkDirectionalArrowRelPos={1}
            linkLabel={(l) => l.label || ''}
            onNodeHover={setHoveredNode}
            onNodeClick={(node) => setSelectedNode(node.id === selectedNode?.id ? null : node)}
            cooldownTicks={80}
            d3AlphaDecay={0.04}
            d3VelocityDecay={0.3}
            width={undefined}
            height={undefined}
          />
        </div>

        {/* ── Right panel: Query + Stats ──────────────── */}
        <div style={{
          width: 360, flexShrink: 0,
          borderLeft: '1px solid var(--border)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
          background: 'var(--surface)',
        }}>

          {/* Stats */}
          <div style={{ padding: '16px 16px 0' }}>
            <p className="overline" style={{ marginBottom: 10 }}>Graph Statistics</p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <StatChip label="Patients" value={statsData?.labels?.Patient} icon={Activity} color="#4F6BEA" />
              <StatChip label="Diseases" value={statsData?.labels?.Disease} icon={AlertCircle} color="#D94040" />
              <StatChip label="Medications" value={statsData?.labels?.Medication} icon={Pill} color="#0EA861" />
              <StatChip label="Lab Tests" value={statsData?.labels?.LabTest} icon={FlaskConical} color="#8B5CF6" />
            </div>
            <div style={{ marginTop: 8 }}>
              <StatChip label="Total Relationships" value={statsData?.relTypesCount ? Object.values(statsData.relTypesCount).reduce((a, b) => a + b, 0) : undefined} icon={GitBranch} color="#C47D0A" />
            </div>
          </div>

          <div style={{ height: 1, background: 'var(--border)', margin: '16px 0' }} />

          {/* Query Interface */}
          <div style={{ padding: '0 16px', flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <p className="overline" style={{ marginBottom: 10 }}>Graph Query (Natural Language)</p>

            <form onSubmit={handleQuery} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ position: 'relative' }}>
                <Search size={13} color="var(--text-3)" style={{
                  position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
                }} />
                <input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask anything about the graph…"
                  style={{
                    width: '100%', padding: '9px 12px 9px 30px',
                    borderRadius: 8, border: '1px solid var(--border)',
                    background: 'var(--surface-2)', color: 'var(--text-1)',
                    fontSize: 12, outline: 'none',
                  }}
                />
              </div>
              <button
                type="submit"
                disabled={queryMutation.isPending || !question.trim()}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
                  padding: '9px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600,
                  background: queryMutation.isPending ? 'var(--brand-dim)' : 'var(--brand)',
                  color: '#fff', border: 'none', cursor: 'pointer', transition: 'all 0.15s',
                  opacity: !question.trim() ? 0.5 : 1,
                }}
              >
                {queryMutation.isPending
                  ? <><Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> Reasoning…</>
                  : <><Zap size={13} /> Ask Knowledge Graph</>
                }
              </button>
            </form>

            {/* Sample prompts */}
            <div style={{ marginTop: 12 }}>
              <p className="caption" style={{ marginBottom: 8 }}>Try these:</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {SAMPLES.map((s) => (
                  <button
                    key={s}
                    onClick={() => setQuestion(s)}
                    style={{
                      textAlign: 'left', padding: '7px 10px', borderRadius: 7,
                      background: 'var(--surface-2)', border: '1px solid var(--border)',
                      color: 'var(--text-2)', fontSize: 11, cursor: 'pointer',
                      transition: 'all 0.12s', display: 'flex', alignItems: 'center', gap: 6,
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--brand-border)'; e.currentTarget.style.color = 'var(--text-1)' }}
                    onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-2)' }}
                  >
                    <ChevronRight size={10} />
                    {s}
                  </button>
                ))}
              </div>
            </div>

            {/* Answer panel */}
            {answer && (
              <div style={{
                marginTop: 14, flex: 1, overflow: 'auto',
                display: 'flex', flexDirection: 'column', gap: 10, minHeight: 0,
              }}>
                <div style={{ height: 1, background: 'var(--border)' }} />

                {/* Cypher block */}
                <div>
                  <p className="caption" style={{ marginBottom: 6, display: 'flex', alignItems: 'center', gap: 5 }}>
                    <GitBranch size={10} /> Generated Cypher
                  </p>
                  <pre style={{
                    padding: '10px 12px', borderRadius: 8, overflow: 'auto',
                    background: 'var(--canvas)', border: '1px solid var(--border)',
                    fontFamily: 'JetBrains Mono, monospace', fontSize: 10.5,
                    color: '#A9C8FF', lineHeight: 1.6, whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  }}>
                    {answer.cypher}
                  </pre>
                </div>

                {/* LLM Answer */}
                <div style={{
                  padding: '12px 14px', borderRadius: 10,
                  background: 'var(--brand-dim)', border: '1px solid var(--brand-border)',
                }}>
                  <p style={{ fontSize: 11, fontWeight: 600, color: 'var(--brand)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 5 }}>
                    <Zap size={10} /> LLM Answer
                  </p>
                  <p style={{ fontSize: 12, color: 'var(--text-1)', lineHeight: 1.7 }}>{answer.answer}</p>
                </div>

                {/* Raw results count */}
                {answer.graph_data?.length > 0 && (
                  <p className="caption" style={{ textAlign: 'center' }}>
                    {answer.graph_data.length} records returned · graph updated ↑
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}
