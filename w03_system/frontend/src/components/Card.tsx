import type { ReactNode } from 'react'

export function Card({ title, children, className = '' }: { title?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg bg-white border border-neutral-200 p-4 space-y-3 ${className}`}>
      {title && <h2 className="text-xs font-medium text-neutral-500">{title}</h2>}
      {children}
    </section>
  )
}
