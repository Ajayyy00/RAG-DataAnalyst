export function Badge({ children, variant = 'default', className = '' }) {
  const variants = {
    default: 'bg-gray-700 text-gray-300',
    success: 'bg-emerald-900/50 text-emerald-400 border border-emerald-500/30',
    danger: 'bg-red-900/50 text-red-400 border border-red-500/30',
    warning: 'bg-amber-900/50 text-amber-400 border border-amber-500/30',
    accent: 'bg-indigo-900/50 text-indigo-300 border border-indigo-500/30',
  }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${variants[variant]} ${className}`}>
      {children}
    </span>
  )
}
