export function Card({ children, className = '' }) {
  return (
    <div
      className={className}
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 4,
      }}
    >
      {children}
    </div>
  )
}
