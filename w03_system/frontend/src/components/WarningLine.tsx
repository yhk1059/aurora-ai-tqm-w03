import { TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'

export function WarningLine({ children, rule }: { children: ReactNode; rule?: string | null }) {
  return (
    <div className="flex items-start gap-2 text-sm text-amber-700">
      <TriangleAlert size={16} strokeWidth={1.5} className="mt-0.5 shrink-0" />
      <span>
        {children}
        {rule && <span className="ml-1.5 font-mono text-xs text-amber-600">{rule}</span>}
      </span>
    </div>
  )
}
