export function Spinner({ size = 'md' }) {
  const s = size === 'lg' ? 24 : 16
  return (
    <svg
      width={s} height={s}
      viewBox="0 0 24 24"
      fill="none"
      stroke="var(--brand)"
      strokeWidth="1.5"
      strokeLinecap="round"
      style={{ animation: 'spin 0.8s linear infinite' }}
    >
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <circle cx="12" cy="12" r="10" strokeOpacity="0.15" />
      <path d="M12 2a10 10 0 0 1 10 10" />
    </svg>
  )
}
