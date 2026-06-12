import { useState } from 'react'
import { ChevronLeft, ChevronRight, Download } from 'lucide-react'

const PAGE = 10

function isNumeric(val) {
  return typeof val === 'number' || (typeof val === 'string' && val !== '' && !isNaN(Number(val)))
}

function detectNumericCols(columns, rows) {
  const sample = rows.slice(0, 5)
  return columns.reduce((acc, col) => {
    const vals = sample.map((r) => (typeof r === 'object' && !Array.isArray(r) ? r[col] : r[columns.indexOf(col)]))
    acc[col] = vals.every(isNumeric)
    return acc
  }, {})
}

function fmtVal(val, isNum) {
  if (val === null || val === undefined) return <span style={{ color: 'var(--text-3)' }}>—</span>
  if (isNum && typeof val === 'number') return val.toLocaleString(undefined, { maximumFractionDigits: 2 })
  return String(val)
}

export default function ResultTable({ columns = [], rows = [], rowCount = 0 }) {
  const [page, setPage] = useState(0)
  if (!columns.length) return null

  const numericCols = detectNumericCols(columns, rows)
  const totalPages  = Math.ceil(rows.length / PAGE)
  const pageRows    = rows.slice(page * PAGE, (page + 1) * PAGE)

  return (
    <div className="data-panel">
      {/* Header */}
      <div className="data-panel-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="overline">Results</span>
          <span className="caption" style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 10 }}>
            {rowCount.toLocaleString()} row{rowCount !== 1 ? 's' : ''}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {totalPages > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0} className="btn-ghost">
                <ChevronLeft size={12} strokeWidth={1.5} />
              </button>
              <span className="caption" style={{ minWidth: 50, textAlign: 'center', fontFamily: '"JetBrains Mono", monospace', fontSize: 10 }}>
                {page + 1} / {totalPages}
              </span>
              <button onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1} className="btn-ghost">
                <ChevronRight size={12} strokeWidth={1.5} />
              </button>
            </div>
          )}
          <button className="btn-ghost" title="Export CSV">
            <Download size={12} strokeWidth={1.5} />
          </button>
        </div>
      </div>

      {/* Table */}
      <div style={{ overflowX: 'auto', maxHeight: 280, overflowY: 'auto' }}>
        <table className="dt">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col} className={numericCols[col] ? 'r' : ''}>
                  {col.replace(/_/g, ' ')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, i) => (
              <tr key={i}>
                {columns.map((col, ci) => {
                  const val = typeof row === 'object' && !Array.isArray(row) ? row[col] : row[ci]
                  const isNum = numericCols[col]
                  return (
                    <td key={col} className={[isNum ? 'r' : '', ci === 0 ? 'highlight' : ''].filter(Boolean).join(' ')}>
                      {fmtVal(val, isNum)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
