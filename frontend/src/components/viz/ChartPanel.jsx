import {
  BarChart, Bar, LineChart, Line, Area, AreaChart,
  PieChart, Pie, Cell, ScatterChart, Scatter,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, LabelList,
} from 'recharts'

// ── Palette ────────────────────────────────────────────────
const PALETTE = [
  '#4F6BEA', '#0EA861', '#F59E0B', '#E05858',
  '#8B5CF6', '#06B6D4', '#F97316', '#10B981',
]
const BRAND = PALETTE[0]

// ── Helpers ────────────────────────────────────────────────
const fmt = (v) => {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') {
    if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M'
    if (v >= 1_000)     return (v / 1_000).toFixed(1) + 'K'
    if (v % 1 !== 0)    return v.toFixed(2)
    return v.toLocaleString()
  }
  return String(v)
}

const truncate = (s, n = 14) =>
  typeof s === 'string' && s.length > n ? s.slice(0, n) + '…' : s

// ── Axis style ─────────────────────────────────────────────
const AXIS = {
  tick: { fontSize: 10, fontFamily: '"JetBrains Mono", monospace', fill: '#4E5D78' },
  axisLine: { stroke: 'rgba(255,255,255,0.06)' },
  tickLine: false,
}

// ── Tooltip ────────────────────────────────────────────────
function Tip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: '#111827',
      border: '1px solid rgba(255,255,255,0.10)',
      borderRadius: 4, padding: '8px 12px',
      fontFamily: "'Plus Jakarta Sans', sans-serif",
      minWidth: 160, maxWidth: 280,
      boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
    }}>
      {label && (
        <p style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.04em',
          textTransform: 'uppercase', color: '#6B7280',
          marginBottom: 6, wordBreak: 'break-word',
        }}>{label}</p>
      )}
      {payload.map((p, i) => (
        <div key={i} style={{
          display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', gap: 16, marginBottom: 2,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{
              width: 6, height: 6, borderRadius: '50%',
              background: p.color || BRAND, flexShrink: 0,
            }} />
            <span style={{ fontSize: 11, color: '#9CA3AF' }}>{p.name}</span>
          </div>
          <span style={{
            fontFamily: '"JetBrains Mono", monospace',
            fontSize: 12, fontWeight: 600, color: p.color || BRAND,
          }}>{fmt(p.value)}</span>
        </div>
      ))}
    </div>
  )
}

// ── KPI card ───────────────────────────────────────────────
function KPICard({ config }) {
  const { data, yKey, xKey } = config
  const val = data?.[0]?.[yKey] ?? data?.[0]?.[xKey] ?? config.value ?? '—'
  const label = data?.[0]?.[xKey] || config.label || yKey
  return (
    <div style={{ padding: '32px 0', textAlign: 'center' }}>
      <p style={{
        fontFamily: '"JetBrains Mono", monospace',
        fontSize: 48, fontWeight: 600,
        color: 'var(--text-1)', letterSpacing: '-0.02em', lineHeight: 1,
      }}>{fmt(val)}</p>
      {label && (
        <p style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 10 }}>{label}</p>
      )}
    </div>
  )
}

// ── Empty state ────────────────────────────────────────────
function Empty({ reason }) {
  return (
    <div style={{
      height: 160, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      color: 'var(--text-3)', fontSize: 12, gap: 6,
    }}>
      <p style={{ fontSize: 22 }}>📊</p>
      <p>{reason || 'No data to display'}</p>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────
export default function ChartPanel({ chartType, chartConfig }) {
  // Guard: need both type and config
  if (!chartType || !chartConfig) return null

  const { data, xKey, yKey, series_keys, yKeys, title } = chartConfig

  // Determine which Y-keys to plot
  const keys = (() => {
    if (series_keys?.length) return series_keys
    if (yKeys?.length)       return yKeys
    if (yKey)                return [yKey]
    return []
  })()

  // Sanitise data: coerce numeric strings → numbers, drop null rows
  const cleanData = Array.isArray(data)
    ? data
        .filter(row => row && typeof row === 'object')
        .map(row => {
          const out = { ...row }
          keys.forEach(k => {
            const v = out[k]
            if (v !== null && v !== undefined && v !== '') {
              const n = Number(v)
              if (!isNaN(n)) out[k] = n
            }
          })
          return out
        })
    : []

  if (!cleanData.length) return <Empty reason="Query returned no rows" />
  if (!keys.length)      return <Empty reason="No numeric column detected" />

  const H = 260
  const multiSeries = keys.length > 1
  const allValues = cleanData.map(d => {
    const v = d[keys[0]]
    return (v === null || v === undefined) ? 0 : Number(v) || 0
  })
  const maxVal = Math.max(...allValues)
  const minVal = Math.min(...allValues)
  const isUniform = maxVal === minVal // Don't highlight if all bars are exactly the same height

  // Detect long x labels → angle them
  const longestLabel = cleanData.reduce((max, d) => {
    const l = String(d[xKey] || '').length
    return l > max ? l : max
  }, 0)
  const angleLabels = longestLabel > 10

  // Label formatter for XAxis
  const xFormatter = (v) => {
    if (typeof v === 'string' && v.length > 12) return v.slice(0, 12) + '…'
    return v
  }

  // ── Render by chart type ────────────────────────────────
  const renderChart = () => {

    // PIE ─────────────────────────────────────────────────
    if (chartType === 'pie') {
      return (
        <ResponsiveContainer width="100%" height={H + 20}>
          <PieChart>
            <Pie
              data={cleanData}
              dataKey={keys[0]}
              nameKey={xKey || 'name'}
              cx="50%" cy="47%"
              innerRadius={60} outerRadius={105}
              paddingAngle={3}
              stroke="none"
            >
              {cleanData.map((_, i) => (
                <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
              ))}
            </Pie>
            <Tooltip content={<Tip />} />
            <Legend
              formatter={(v) => <span style={{ fontSize: 11, color: '#9CA3AF' }}>{truncate(v, 20)}</span>}
              wrapperStyle={{ fontSize: 11 }}
            />
          </PieChart>
        </ResponsiveContainer>
      )
    }

    // SCATTER ─────────────────────────────────────────────
    if (chartType === 'scatter') {
      return (
        <ResponsiveContainer width="100%" height={H}>
          <ScatterChart margin={{ top: 8, right: 20, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
            <XAxis
              dataKey={xKey} type="number" name={xKey}
              tickFormatter={fmt}
              {...AXIS}
            />
            <YAxis dataKey={keys[0]} type="number" name={keys[0]} tickFormatter={fmt} {...AXIS} />
            <Tooltip content={<Tip />} cursor={{ stroke: 'rgba(255,255,255,0.06)' }} />
            <Scatter data={cleanData} fill={BRAND} opacity={0.75} r={5} />
          </ScatterChart>
        </ResponsiveContainer>
      )
    }

    // LINE / AREA ─────────────────────────────────────────
    if (chartType === 'line' || chartType === 'area') {
      return (
        <ResponsiveContainer width="100%" height={H}>
          <AreaChart data={cleanData} margin={{ top: 8, right: 20, bottom: angleLabels ? 48 : 8, left: 0 }}>
            <defs>
              {keys.map((k, i) => (
                <linearGradient key={k} id={'grad_' + i} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"   stopColor={PALETTE[i % PALETTE.length]} stopOpacity={0.18} />
                  <stop offset="100%" stopColor={PALETTE[i % PALETTE.length]} stopOpacity={0}    />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
            <XAxis
              dataKey={xKey}
              tickFormatter={xFormatter}
              angle={angleLabels ? -30 : 0}
              textAnchor={angleLabels ? 'end' : 'middle'}
              height={angleLabels ? 60 : 30}
              interval="preserveStartEnd"
              {...AXIS}
            />
            <YAxis tickFormatter={fmt} width={52} {...AXIS} />
            <Tooltip content={<Tip />} />
            {multiSeries && <Legend formatter={(v) => <span style={{ fontSize: 11, color: '#9CA3AF' }}>{v}</span>} />}
            {keys.map((k, i) => (
              <Area
                key={k} type="monotone" dataKey={k} name={k}
                stroke={PALETTE[i % PALETTE.length]} strokeWidth={2}
                fill={'url(#grad_' + i + ')'}
                dot={{ r: 3, fill: PALETTE[i % PALETTE.length], strokeWidth: 0 }}
                activeDot={{ r: 5, strokeWidth: 0 }}
                connectNulls
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      )
    }

    // HEATMAP — render as coloured table ───────────────────
    if (chartType === 'heatmap') {
      const allCols = Object.keys(cleanData[0] || {})
      const numCols = allCols.filter(c => c !== xKey && typeof cleanData[0][c] === 'number')
      const allVals = cleanData.flatMap(d => numCols.map(c => Number(d[c]) || 0))
      const localMax = Math.max(...allVals) || 1
      return (
        <div style={{ overflowX: 'auto', maxHeight: H, overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <thead>
              <tr>
                {allCols.map(c => (
                  <th key={c} style={{
                    padding: '5px 10px', textAlign: 'left',
                    color: '#4E5D78', fontFamily: '"JetBrains Mono",monospace',
                    fontSize: 10, borderBottom: '1px solid rgba(255,255,255,0.06)',
                    position: 'sticky', top: 0, background: 'var(--surface)',
                  }}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cleanData.map((row, ri) => (
                <tr key={ri}>
                  {allCols.map((c, ci) => {
                    const v = row[c]
                    const intensity = numCols.includes(c) && localMax > 0
                      ? (Number(v) || 0) / localMax : 0
                    return (
                      <td key={ci} style={{
                        padding: '5px 10px', color: 'var(--text-2)',
                        fontFamily: ci > 0 ? '"JetBrains Mono",monospace' : undefined,
                        fontSize: 11,
                        background: intensity > 0 ? `rgba(79,107,234,${intensity * 0.4})` : 'transparent',
                        borderBottom: '1px solid rgba(255,255,255,0.03)',
                      }}>{v ?? '—'}</td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }

    // BAR (default) ───────────────────────────────────────
    return (
      <ResponsiveContainer width="100%" height={H}>
        <BarChart
          data={cleanData}
          margin={{ top: 8, right: 20, bottom: angleLabels ? 56 : 8, left: 0 }}
          barCategoryGap="32%"
          barGap={4}
        >
          <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
          <XAxis
            dataKey={xKey}
            tickFormatter={xFormatter}
            angle={angleLabels ? -35 : 0}
            textAnchor={angleLabels ? 'end' : 'middle'}
            height={angleLabels ? 70 : 30}
            interval={0}
            {...AXIS}
          />
          <YAxis
            tickFormatter={fmt}
            width={52}
            domain={[0, dataMax => Math.ceil(Math.max(dataMax * 1.1, 5))]}
            {...AXIS}
          />
          <Tooltip content={<Tip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
          {multiSeries && (
            <Legend
              wrapperStyle={{ paddingTop: 12 }}
              formatter={(v) => <span style={{ fontSize: 11, color: '#9CA3AF' }}>{v}</span>}
            />
          )}
          {keys.map((k, i) => (
            <Bar
              key={k} dataKey={k} name={k}
              radius={[3, 3, 0, 0]}
              maxBarSize={multiSeries ? 24 : 40}
              minPointSize={2}
              isAnimationActive
            >
              {!multiSeries
                ? cleanData.map((entry, idx) => (
                    <Cell
                      key={idx}
                      fill={
                        (entry[k] === maxVal && maxVal > 0 && !isUniform)
                          ? PALETTE[i % PALETTE.length]
                          : `rgba(79,107,234,0.38)`
                      }
                    />
                  ))
                : null}
              {!multiSeries && cleanData.length <= 8 && (
                <LabelList
                  dataKey={k}
                  position="top"
                  formatter={fmt}
                  style={{
                    fontFamily: '"JetBrains Mono",monospace',
                    fontSize: 9, fill: '#6B7280',
                  }}
                />
              )}
              {multiSeries && (
                <Cell fill={PALETTE[i % PALETTE.length]} />
              )}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    )
  }

  const typeLabel = {
    bar: 'Bar', line: 'Line', area: 'Area', pie: 'Pie',
    scatter: 'Scatter', heatmap: 'Heatmap', kpi: 'KPI',
  }[chartType] || chartType

  return (
    <div className="data-panel">
      <div className="data-panel-header">
        <span className="overline">
          {title || ('Chart — ' + typeLabel)}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{
            fontSize: 9, fontWeight: 700, letterSpacing: '0.06em',
            textTransform: 'uppercase', color: 'var(--brand)',
            padding: '2px 6px', border: '1px solid rgba(79,107,234,0.25)',
            borderRadius: 2,
          }}>{typeLabel}</span>
          <span className="caption" style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 10 }}>
            {cleanData.length} rows
          </span>
        </div>
      </div>
      <div style={{ padding: '12px 8px 8px' }}>
        {chartType === 'kpi' ? <KPICard config={{ ...chartConfig, data: cleanData, yKey: keys[0] }} /> : renderChart()}
      </div>
    </div>
  )
}
